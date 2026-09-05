import sys
from pathlib import Path

# Ensure backend root is on sys.path for direct CLI execution
_backend_dir = str(Path(__file__).resolve().parents[2])
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

import asyncio
import json
import logging
import os
import re
import time
from typing import Dict, Any, Optional, List, Callable

from pi_agent.agent import Agent
from pi_agent.config import AgentConfig
from pi_agent.sandbox import Sandbox
from pi_agent.tools.base import Tool
from pi_agent.tools.registry import ToolRegistry
from pi_agent.llm import (
    LLMProvider,
    AssistantResponse,
    ToolCall,
    NeutralMessage,
    OpenAIProvider,
    build_provider,
    detect_provider,
)

from app.config import settings
from app.rag.retriever import RAGService
from app.rag.query_rewriter import QueryRewriter
from app.providers.provider_factory import get_active_provider_name, get_provider
from app.agent.tools import (
    build_podcast_rag_tool,
    build_ship30_tool,
    set_main_event_loop,
    PodcastRAGTool,
    Ship30Tool,
    AgentResponse,
)
from app.agent.exceptions import (
    AgentValidationError,
    AgentExecutionError,
    ToolNotFoundError,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Provider Wrapper with Local Model Fallback Handling
# =============================================================================

class PiLLMProviderAdapter:
    """Wraps an LLMProvider to ensure tool calls from smaller local models
    (such as Llama 3.2 3B in Ollama that emit JSON text) are normalized
    into standard Pi Coding Agent ToolCalls.
    """

    def __init__(self, base_provider: LLMProvider):
        self._provider = base_provider
        self.name = getattr(base_provider, "name", "adapter")
        self.model = getattr(base_provider, "model", "unknown")

    @property
    def supports_streaming(self) -> bool:
        return getattr(self._provider, "supports_streaming", False)

    def complete(
        self, system: str, messages: list[NeutralMessage], tools: list[dict[str, Any]]
    ) -> AssistantResponse:
        response = self._provider.complete(system, messages, tools)

        # If native tool_calls are empty but text contains a structured tool call JSON
        # (common for smaller local Ollama models)
        if response.text and not response.tool_calls:
            parsed_call = self._extract_json_tool_call(response.text, tools)
            if parsed_call:
                response.tool_calls.append(parsed_call)

        # Ensure tool call arguments have fallback to user query if model omitted them
        if response.tool_calls:
            last_user_msg = ""
            for m in reversed(messages):
                role = m.get("role") if isinstance(m, dict) else getattr(m, "role", None)
                if role == "user":
                    last_user_msg = m.get("content", "") if isinstance(m, dict) else getattr(m, "content", "")
                    break

            clean_lower = last_user_msg.lower()
            writing_keywords = [
                "ship30", "ship 30", "article", "essay", "blog post",
                "blog", "long-form", "long form", "newsletter"
            ]
            is_writing = any(kw in clean_lower for kw in writing_keywords) or (
                any(w in clean_lower for w in ["write", "draft", "compose"]) and ("post" in clean_lower or "piece" in clean_lower)
            )

            for tc in response.tool_calls:
                # Redirect writing requests to Ship30Tool if misrouted
                if is_writing and tc.name == "PodcastRAGTool":
                    tc.name = "Ship30Tool"
                    tc.args = {"topic": tc.args.get("question") or last_user_msg}

                if tc.name == "Ship30Tool" and not tc.args.get("topic"):
                    tc.args["topic"] = last_user_msg
                elif tc.name == "PodcastRAGTool" and not tc.args.get("question"):
                    tc.args["question"] = last_user_msg

        return response

    @staticmethod
    def _extract_json_tool_call(text: str, tools: list[dict[str, Any]]) -> Optional[ToolCall]:
        """Extracts JSON tool invocation from model response text if present."""
        known_names = {t.get("name") for t in tools}
        clean_text = text.strip()

        # Check for JSON object in text
        match = re.search(r"\{[\s\S]*\}", clean_text)
        if not match:
            return None

        try:
            data = json.loads(match.group(0))
            name = data.get("name") or data.get("tool")
            args = data.get("parameters") or data.get("arguments") or data.get("args") or {}

            if name in known_names:
                return ToolCall(id=f"call_{int(time.time())}", name=name, args=args)
        except Exception:
            pass

        # Resilient fallback extraction if JSON was slightly malformed by small local models
        for tool_name in known_names:
            if tool_name in clean_text:
                q_match = re.search(r'["\'](?:question|topic|query)["\']\s*:\s*["\']([^"\']+)["\']', clean_text)
                extracted_arg = q_match.group(1) if q_match else ""
                args = {"question": extracted_arg} if tool_name == "PodcastRAGTool" else {"topic": extracted_arg}
                return ToolCall(id=f"call_{int(time.time())}", name=tool_name, args=args)

        return None


def get_current_pi_provider(force_local: bool = False) -> LLMProvider:
    """Instantiates the active LLM provider for Pi Coding Agent.
    
    Checks dynamic runtime provider setting ('cloud' vs 'ollama').
    When 'cloud' is selected, connects to OpenRouter / Claude.
    When 'ollama' is selected (or if cloud fails and fallback is requested),
    uses local Ollama with llama3.2:3b.
    """
    active_name = "ollama" if force_local else get_active_provider_name()

    if active_name == "cloud":
        key = (
            getattr(settings, "OPENROUTER_API_KEY", "")
            or os.getenv("OPENROUTER_API_KEY")
            or os.getenv("ANTHROPIC_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or ""
        )
        if key:
            try:
                base_url = (
                    getattr(settings, "OPENROUTER_BASE_URL", "")
                    or os.getenv("OPENROUTER_BASE_URL")
                    or "https://openrouter.ai/api/v1"
                )
                cloud_model = (
                    getattr(settings, "CLOUD_MODEL", "")
                    or os.getenv("CLOUD_MODEL")
                    or "anthropic/claude-sonnet-4"
                )
                logger.info(
                    "Instantiating Cloud provider for Agent: model='%s', base_url='%s'",
                    cloud_model,
                    base_url,
                )
                provider = OpenAIProvider(
                    model=cloud_model,
                    api_key=key,
                    base_url=base_url,
                    max_tokens=4096,
                )
                return PiLLMProviderAdapter(provider)
            except Exception as exc:
                logger.error("Failed to build cloud provider for agent: %s. Falling back to local.", exc)

    # Local Ollama Provider (Mandatory Demo)
    model_name = getattr(settings, "OLLAMA_DEFAULT_MODEL", "llama3.2:3b")
    try:
        provider = build_provider(model_name, "ollama")
        return PiLLMProviderAdapter(provider)
    except Exception as exc:
        logger.warning("Failed to initialize Ollama provider: %s. Using default detection.", exc)
        detected = detect_provider()
        provider = build_provider(model_name, detected)
        return PiLLMProviderAdapter(provider)


def get_default_llm_provider() -> LLMProvider:
    """Instantiates the default LLM provider based on active settings."""
    return get_current_pi_provider()


# =============================================================================
# LennyAgent Orchestrator
# =============================================================================

LENNY_AGENT_SYSTEM_PROMPT = """You are the primary Lenny AI Assistant orchestrator agent built on the Pi Coding Agent framework.
You have access to two specialized tools:

1. 'PodcastRAGTool': Use this tool to answer general user questions, inquiries, and requests for advice on product management, feature prioritization, customer retention, growth loops, metrics, and startup strategy using Lenny's Podcast transcripts.
2. 'Ship30Tool': Use this tool whenever the user requests:
   - Ship30 article
   - Ship30 essay
   - blog post
   - long-form content
   - newsletter
   - or requests to write, draft, compose, or author an article, essay, or post.

Guidelines:
- Analyze the user's intent carefully.
- For ANY writing request (Ship30 article, Ship30 essay, blog post, long-form content, newsletter, article, essay), ALWAYS call 'Ship30Tool'.
- For knowledge questions, advice, and inquiries, ALWAYS call 'PodcastRAGTool'.
- Only call the single best tool for the user request.
"""


class LennyAgent:
    """Primary orchestrator agent built with the Pi Coding Agent SDK.
    Dispatches user requests to registered tools (PodcastRAGTool, Ship30Tool)
    via the SDK's native tool registration and ReAct execution loop.
    """

    def __init__(
        self,
        provider: Optional[LLMProvider] = None,
        podcast_tool: Optional[Any] = None,
        ship30_tool: Optional[Any] = None,
        tools: Optional[Dict[str, Any]] = None,
        workspace_dir: str = ".",
        query_rewriter: Optional[QueryRewriter] = None,
    ):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.sandbox = Sandbox(workspace_dir)
        self._custom_provider = provider
        self.query_rewriter = query_rewriter or QueryRewriter()

        # Build native Pi Coding Agent tools
        self._raw_podcast_tool = podcast_tool or build_podcast_rag_tool()
        self._raw_ship30_tool = ship30_tool or build_ship30_tool()

        initial_tools: List[Tool] = []
        initial_tools.append(self._to_pi_tool("PodcastRAGTool", self._raw_podcast_tool))
        initial_tools.append(self._to_pi_tool("Ship30Tool", self._raw_ship30_tool))

        if tools:
            for name, t in tools.items():
                initial_tools.append(self._to_pi_tool(name, t))

        self.registry = ToolRegistry(initial_tools)
        self.config = AgentConfig(
            system_prompt=LENNY_AGENT_SYSTEM_PROMPT,
            stream=False,
            max_iterations=5,
            auto_approve=True,
            enable_shell=False,
        )

        self.logger.info(
            "initialized with Pi Coding Agent SDK",
            extra={"registered_tools": self.registry.names()}
        )

    @property
    def provider(self) -> LLMProvider:
        if self._custom_provider is not None:
            return self._custom_provider
        return get_current_pi_provider()

    @provider.setter
    def provider(self, val: Optional[LLMProvider]) -> None:
        self._custom_provider = val

    # -------------------------------------------------------------------------
    # Tool Conversion & Registry Management
    # -------------------------------------------------------------------------

    def _to_pi_tool(self, name: str, tool_obj: Any) -> Tool:
        """Ensures the tool object conforms to a native Pi Coding Agent Tool."""
        if isinstance(tool_obj, Tool):
            return tool_obj

        # If wrapped class (e.g. PodcastRAGTool or Ship30Tool)
        if hasattr(tool_obj, "tool") and isinstance(tool_obj.tool, Tool):
            return tool_obj.tool

        # If mock or callable with .run
        if hasattr(tool_obj, "run"):
            def generic_handler(args: Dict[str, Any], sandbox: Sandbox) -> str:
                res = tool_obj.run(**args)
                if asyncio.iscoroutine(res):
                    from app.agent.tools import _run_async
                    res = _run_async(res)
                if isinstance(res, dict):
                    return json.dumps(res)
                return str(res)

            return Tool(
                name=name,
                description=getattr(tool_obj, "description", f"Tool {name}"),
                input_schema=getattr(tool_obj, "input_schema", {"type": "object"}),
                handler=generic_handler,
            )

        raise ValueError(f"Cannot convert object {tool_obj} to a Pi Coding Agent Tool.")

    def register_tool(self, name: str, tool: Any) -> None:
        """Registers an additional or replacement tool in the Pi ToolRegistry."""
        pi_tool = self._to_pi_tool(name, tool)
        self.registry.extend([pi_tool])
        self.logger.debug("Registered tool with Pi ToolRegistry", extra={"tool_name": name})

    def get_tool(self, name: str) -> Optional[Tool]:
        """Retrieves a registered Tool from the registry."""
        return self.registry.get(name)

    def list_tools(self) -> List[str]:
        """Returns all registered tool names."""
        return self.registry.names()

    @property
    def podcast_tool(self) -> Optional[Tool]:
        return self.registry.get("PodcastRAGTool")

    @podcast_tool.setter
    def podcast_tool(self, tool: Any) -> None:
        self.register_tool("PodcastRAGTool", tool)

    @property
    def ship30_tool(self) -> Optional[Tool]:
        return self.registry.get("Ship30Tool")

    @ship30_tool.setter
    def ship30_tool(self, tool: Any) -> None:
        self.register_tool("Ship30Tool", tool)

    @property
    def tools(self) -> Dict[str, Tool]:
        return self.registry._tools

    # -------------------------------------------------------------------------
    # Execution via Pi Coding Agent SDK
    # -------------------------------------------------------------------------

    async def run(
        self,
        user_input: str,
        top_k: int = 6,
        chat_history: Optional[List[Dict[str, str]]] = None,
    ) -> AgentResponse:
        """Orchestrates request execution via the Pi Coding Agent SDK ReAct loop."""
        t0 = time.time()

        # Input validation
        if not user_input or not isinstance(user_input, str) or not user_input.strip():
            self.logger.warning("Empty or invalid user input received")
            raise AgentValidationError("User request must be a non-empty string.")

        clean_input = user_input.strip()
        original_query = clean_input

        # Ensure active event loop is registered for thread-safe cross-thread scheduling
        try:
            current_loop = asyncio.get_running_loop()
            set_main_event_loop(current_loop)
        except Exception:
            pass

        # 1. Conversational Query Rewriting if chat history is available
        rewritten_query = clean_input
        if chat_history and len(chat_history) > 0:
            try:
                rewritten_query = await self.query_rewriter.rewrite(clean_input, chat_history)
            except Exception as exc:
                self.logger.warning("Query rewriting failed: %s", exc)
                rewritten_query = clean_input

        self.logger.info(
            "Agent processing query\n"
            "  Original query: '%s'\n"
            "  Rewritten query: '%s'",
            original_query, rewritten_query,
            extra={
                "original_query": original_query,
                "rewritten_query": rewritten_query,
                "history_turns": len(chat_history) if chat_history else 0
            }
        )

        selected_tool: Optional[str] = None
        tool_raw_output: Optional[str] = None
        executed_calls: List[ToolCall] = []

        def on_event(kind: str, payload: Any) -> None:
            nonlocal selected_tool, tool_raw_output
            if kind == "tool_call":
                selected_tool = payload.name
                executed_calls.append(payload)
                self.logger.info(
                    "Pi Coding Agent dispatched tool call: %s | Args: %s",
                    payload.name, payload.args,
                    extra={"tool": payload.name, "tool_args": payload.args}
                )
            elif kind == "tool_result":
                tool_raw_output = payload.get("output")
                self.logger.debug("Pi Coding Agent received tool result", extra={"tool": payload.get("call", {}).name})

        # Instantiate native Pi Coding Agent
        pi_agent_instance = Agent(
            provider=self.provider,
            registry=self.registry,
            sandbox=self.sandbox,
            config=self.config,
            on_event=on_event,
        )

        try:
            # Offload synchronous pi_agent execution to thread pool with rewritten query
            final_text = await asyncio.to_thread(pi_agent_instance.run, rewritten_query)
        except Exception as exc:
            # Automatic Fallback: If cloud failed and fallback to local is enabled, retry with local Ollama
            active_p = get_active_provider_name()
            if active_p == "cloud" and getattr(settings, "FALLBACK_TO_LOCAL", True):
                self.logger.warning(
                    "Cloud provider execution failed in LennyAgent: %s. Automatically falling back to local Ollama...",
                    exc,
                )
                try:
                    fallback_provider = get_current_pi_provider(force_local=True)
                    fallback_instance = Agent(
                        provider=fallback_provider,
                        registry=self.registry,
                        sandbox=self.sandbox,
                        config=self.config,
                        on_event=on_event,
                    )
                    final_text = await asyncio.to_thread(fallback_instance.run, rewritten_query)
                    self.logger.info("Successfully executed query via local Ollama fallback!")
                except Exception as fallback_exc:
                    duration = round(time.time() - t0, 3)
                    self.logger.error(
                        "Local Ollama fallback also failed: %s",
                        fallback_exc,
                        extra={"duration_s": duration, "input": rewritten_query},
                        exc_info=True,
                    )
                    raise AgentExecutionError(f"Both Cloud and Local providers failed: {fallback_exc}") from fallback_exc
            else:
                duration = round(time.time() - t0, 3)
                self.logger.error(
                    "Pi Coding Agent orchestration failed: %s",
                    exc,
                    extra={"duration_s": duration, "input": rewritten_query},
                    exc_info=True
                )
                raise AgentExecutionError(f"Pi Coding Agent execution error: {exc}") from exc

        # Extract answer and sources
        answer = final_text
        sources: List[str] = []
        artifact = False
        markdown_content = None
        html_content = None

        word_count = None
        # If a tool was executed, extract structured output
        if tool_raw_output:
            try:
                parsed_data = json.loads(tool_raw_output)
                if isinstance(parsed_data, dict):
                    # If model returned a summary/synthesis, keep it; otherwise use tool answer
                    tool_answer = parsed_data.get("answer", "")
                    if selected_tool == "Ship30Tool" and tool_answer:
                        answer = tool_answer
                    elif tool_answer and (not final_text or final_text.startswith("Stopped:")):
                        answer = tool_answer
                    elif tool_answer and len(final_text) < len(tool_answer) * 0.5:
                        answer = tool_answer

                    sources = parsed_data.get("sources", [])
                    artifact = bool(parsed_data.get("artifact", False))
                    markdown_content = parsed_data.get("markdown_content")
                    html_content = parsed_data.get("html_content")
                    word_count = parsed_data.get("word_count")
            except Exception:
                if not answer:
                    answer = tool_raw_output

        # If Ship30Tool ran and returned a valid article, ensure artifact flag and formats are set
        if selected_tool == "Ship30Tool" and answer and "not enough transcript evidence available" not in answer.lower():
            artifact = True
            if not markdown_content:
                markdown_content = answer
            if not html_content:
                try:
                    from markdown_it import MarkdownIt
                    html_content = f'<article class="ship30-article">\n{MarkdownIt().render(markdown_content)}\n</article>'
                except Exception:
                    html_content = f'<article class="ship30-article">\n<div>{markdown_content}</div>\n</article>'
            if word_count is None and markdown_content:
                word_count = len(markdown_content.strip().split())

        # Fallback if no tool was called (direct response)
        if not selected_tool:
            selected_tool = "DirectResponse"

        self.logger.info("Agent selected tool: '%s' | Artifact: %s | Word Count: %s", selected_tool, artifact, word_count)

        duration = round(time.time() - t0, 3)
        self.logger.info(
            "Completed via Pi Coding Agent",
            extra={
                "selected_tool": selected_tool,
                "duration_s": duration,
                "sources_count": len(sources),
                "answer_length": len(answer),
                "artifact": artifact,
                "word_count": word_count,
            }
        )

        return AgentResponse(
            selected_tool=selected_tool,
            answer=answer,
            sources=sources,
            artifact=artifact,
            markdown_content=markdown_content,
            html_content=html_content,
            word_count=word_count,
        )


# Backward compatibility alias
GrowthAgent = LennyAgent


# =============================================================================
# Direct CLI Entry Point
# =============================================================================

if __name__ == "__main__":
    import asyncio
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    raw_args = sys.argv[1:]
    use_mock = "--mock" in raw_args
    filtered_args = [a for a in raw_args if a != "--mock"]

    query = " ".join(filtered_args) if filtered_args else "How should product teams prioritize features?"
    print("\n" + "=" * 60)
    print("LENNY AI ASSISTANT - PI CODING AGENT CLI")
    print("=" * 60)
    print(f"User Query: {query}\n")

    provider = None
    if use_mock:
        class MockPiProvider(LLMProvider):
            name = "mock"
            model = "mock-model"
            supports_streaming = False

            def complete(self, system: str, messages: list[NeutralMessage], tools: list[dict[str, Any]]) -> AssistantResponse:
                last_msg = messages[-1]
                # If tool result returned, return final answer
                if last_msg.get("role") == "tool":
                    output_str = last_msg["results"][0].output
                    try:
                        data = json.loads(output_str)
                        return AssistantResponse(text=data.get("answer", output_str))
                    except Exception:
                        return AssistantResponse(text=output_str)

                # Route based on prompt
                user_content = last_msg.get("content", "").lower()
                if "write" in user_content or "ship30" in user_content or "article" in user_content or "essay" in user_content:
                    return AssistantResponse(
                        text="",
                        tool_calls=[ToolCall(id="call_1", name="Ship30Tool", args={"topic": last_msg["content"]})]
                    )
                else:
                    return AssistantResponse(
                        text="",
                        tool_calls=[ToolCall(id="call_1", name="PodcastRAGTool", args={"question": last_msg["content"], "top_k": 5})]
                    )

        provider = MockPiProvider()
        print("[Mode: Mock / Offline Provider]\n")

    agent = LennyAgent(provider=provider)

    try:
        response = asyncio.run(agent.run(query))
        print("=" * 60)
        print(f"Selected Tool : {response.selected_tool}")
        print("=" * 60)
        print(f"Answer:\n\n{response.answer}\n")
        if response.sources:
            print("=" * 60)
            print("Sources:")
            for s in response.sources:
                print(f"  * {s}")
        print("=" * 60 + "\n")
    except Exception as exc:
        print(f"\n[Agent Error]: {exc}\n")
