import json
import pytest
from typing import Any, List, Dict
from unittest.mock import AsyncMock, MagicMock, patch

from pi_agent.tools.base import Tool, Sandbox
from pi_agent.tools.registry import ToolRegistry
from pi_agent.llm import LLMProvider, AssistantResponse, ToolCall, NeutralMessage

from app.agent import (
    LennyAgent,
    GrowthAgent,
    PodcastRAGTool,
    Ship30Tool,
    build_podcast_rag_tool,
    build_ship30_tool,
    AgentResponse,
    AgentError,
    AgentValidationError,
    AgentExecutionError,
    ToolNotFoundError,
)
from app.rag.retriever import RAGResponse, RetrievalResult
from app.skills.ship30_writer import (
    Ship30Writer,
    Ship30Result,
    SECTION_TARGETS,
    count_words,
    parse_markdown_sections,
    reconstruct_markdown,
    SHIP_30_PROMPT_TEMPLATE,
)


# =============================================================================
# Mock LLM Provider for SDK Tool Routing Tests
# =============================================================================

class MockSDKProvider(LLMProvider):
    """Deterministic mock provider that simulates the LLM's tool-call decisions
    within the Pi Coding Agent SDK framework.
    """

    name = "mock_sdk"
    model = "mock-model"
    supports_streaming = False

    def __init__(self, target_tool: str = "PodcastRAGTool", final_text: str = ""):
        self.target_tool = target_tool
        self.final_text = final_text
        self.turns = 0

    def complete(
        self, system: str, messages: List[NeutralMessage], tools: List[Dict[str, Any]]
    ) -> AssistantResponse:
        self.turns += 1
        last_msg = messages[-1]

        # If previous message is a tool result, return final synthesized text
        if last_msg.get("role") == "tool":
            output_raw = last_msg["results"][0].output
            try:
                data = json.loads(output_raw)
                return AssistantResponse(
                    text=self.final_text or data.get("answer", output_raw)
                )
            except Exception:
                return AssistantResponse(text=self.final_text or output_raw)

        # Initial turn: Model inspects prompt and dispatches tool call
        user_text = last_msg.get("content", "")
        if self.target_tool == "Ship30Tool":
            return AssistantResponse(
                text="",
                tool_calls=[ToolCall(id="call_ship30", name="Ship30Tool", args={"topic": user_text})]
            )
        else:
            return AssistantResponse(
                text="",
                tool_calls=[ToolCall(id="call_rag", name="PodcastRAGTool", args={"question": user_text, "top_k": 5})]
            )


# =============================================================================
# SDK Tool Registration & Schema Tests
# =============================================================================

def test_sdk_tool_registration_types():
    """Verifies that tools are registered as native Pi Coding Agent Tool objects."""
    agent = LennyAgent(provider=MockSDKProvider())
    assert "PodcastRAGTool" in agent.list_tools()
    assert "Ship30Tool" in agent.list_tools()

    podcast_tool = agent.get_tool("PodcastRAGTool")
    ship30_tool = agent.get_tool("Ship30Tool")

    assert isinstance(podcast_tool, Tool)
    assert isinstance(ship30_tool, Tool)
    assert podcast_tool.name == "PodcastRAGTool"
    assert ship30_tool.name == "Ship30Tool"


def test_sdk_tool_schemas():
    """Verifies that tools produce provider-neutral JSON schemas for the SDK."""
    podcast_tool = build_podcast_rag_tool()
    ship30_tool = build_ship30_tool()

    schema_podcast = podcast_tool.to_schema()
    schema_ship30 = ship30_tool.to_schema()

    # Verify PodcastRAGTool schema
    assert schema_podcast["name"] == "PodcastRAGTool"
    assert "question" in schema_podcast["input_schema"]["properties"]
    assert "question" in schema_podcast["input_schema"]["required"]
    assert "top_k" in schema_podcast["input_schema"]["properties"]

    # Verify Ship30Tool schema
    assert schema_ship30["name"] == "Ship30Tool"
    assert "topic" in schema_ship30["input_schema"]["properties"]
    assert "topic" in schema_ship30["input_schema"]["required"]


def test_sdk_custom_tool_registration():
    """Verifies dynamic registration of custom tools in the Pi ToolRegistry."""
    agent = LennyAgent(provider=MockSDKProvider())

    custom_tool = Tool(
        name="MarketAnalysisTool",
        description="Analyzes market landscape.",
        input_schema={"type": "object", "properties": {"market": {"type": "string"}}},
        handler=lambda args, sb: "Market Analysis Result"
    )
    agent.register_tool("MarketAnalysisTool", custom_tool)

    assert "MarketAnalysisTool" in agent.list_tools()
    assert agent.get_tool("MarketAnalysisTool") is custom_tool


def test_backward_compatibility_growth_agent_alias():
    """Verifies that GrowthAgent remains available as an alias to LennyAgent."""
    agent = GrowthAgent(provider=MockSDKProvider())
    assert isinstance(agent, LennyAgent)
    assert "PodcastRAGTool" in agent.list_tools()
    assert "Ship30Tool" in agent.list_tools()


# =============================================================================
# SDK Tool Routing & Orchestration Tests
# =============================================================================

@pytest.mark.asyncio
async def test_sdk_intent_routing_to_podcast_rag_tool():
    """Assignment requirement:
    'How should product teams prioritize features?' -> PodcastRAGTool
    Tested through Pi Coding Agent SDK execution loop.
    """
    mock_rag_service = AsyncMock()
    mock_rag_service.answer.return_value = RAGResponse(
        question="How should product teams prioritize features?",
        answer="Prioritize by customer impact and user retention metrics.",
        sources=["Episode 10 | Shreyas Doshi", "Episode 42 | Casey Winters"],
        retrieved_chunks=[]
    )

    provider = MockSDKProvider(target_tool="PodcastRAGTool")
    agent = LennyAgent(
        provider=provider,
        podcast_tool=build_podcast_rag_tool(mock_rag_service)
    )

    response = await agent.run("How should product teams prioritize features?")

    assert response.selected_tool == "PodcastRAGTool"
    assert "Prioritize by customer impact" in response.answer
    assert response.sources == ["Episode 10 | Shreyas Doshi", "Episode 42 | Casey Winters"]


@pytest.mark.asyncio
async def test_sdk_intent_routing_to_ship30_tool():
    """Assignment requirement:
    'Write a Ship30 article about product strategy' -> Ship30Tool
    Tested through Pi Coding Agent SDK execution loop.
    """
    mock_writer = AsyncMock()
    mock_writer.write.return_value = (
        "# The Ruthless Art of Product Strategy\n\n"
        "Most teams fail because they build features instead of outcomes."
    )

    provider = MockSDKProvider(target_tool="Ship30Tool")
    agent = LennyAgent(
        provider=provider,
        ship30_tool=build_ship30_tool(mock_writer)
    )

    response = await agent.run("Write a Ship30 article about product strategy")

    assert response.selected_tool == "Ship30Tool"
    assert "The Ruthless Art of Product Strategy" in response.answer
    assert response.sources == []


@pytest.mark.asyncio
async def test_sdk_direct_response_when_no_tool_called():
    """Verifies that if the model decides to answer directly without tools,
    selected_tool is marked as DirectResponse.
    """
    class DirectResponseProvider(LLMProvider):
        name = "direct"
        model = "direct-model"
        supports_streaming = False

        def complete(self, system: str, messages: List[NeutralMessage], tools: List[Dict[str, Any]]) -> AssistantResponse:
            return AssistantResponse(text="Hello! I am Lenny AI Assistant.")

    agent = LennyAgent(provider=DirectResponseProvider())
    response = await agent.run("Hi there!")

    assert response.selected_tool == "DirectResponse"
    assert response.answer == "Hello! I am Lenny AI Assistant."
    assert response.sources == []


# =============================================================================
# Tool Execution Tests (Handlers Directly)
# =============================================================================

def test_podcast_rag_tool_handler_success():
    """Verifies that PodcastRAGTool handler executes RAGService and returns JSON."""
    mock_rag_service = AsyncMock()
    mock_rag_service.answer.return_value = RAGResponse(
        question="What is PMF?",
        answer="Product Market Fit is when retention flattens.",
        sources=["Episode 20 | Brian Balfour"],
        retrieved_chunks=[]
    )

    tool = build_podcast_rag_tool(mock_rag_service)
    sandbox = Sandbox(".")
    raw_output = tool.handler({"question": "What is PMF?", "top_k": 3}, sandbox)

    data = json.loads(raw_output)
    assert data["answer"] == "Product Market Fit is when retention flattens."
    assert data["sources"] == ["Episode 20 | Brian Balfour"]


def test_ship30_tool_handler_success():
    """Verifies that Ship30Tool handler executes Ship30Writer and returns JSON."""
    mock_writer = AsyncMock()
    mock_writer.write.return_value = "Atomic Essay Content"

    tool = build_ship30_tool(mock_writer)
    sandbox = Sandbox(".")
    raw_output = tool.handler({"topic": "Viral Loops"}, sandbox)

    data = json.loads(raw_output)
    assert data["answer"] == "Atomic Essay Content"
    assert data["sources"] == []


def test_podcast_rag_tool_handler_error_handling():
    """Verifies that tool handler catches internal errors and returns structured error JSON."""
    mock_rag_service = AsyncMock()
    mock_rag_service.answer.side_effect = RuntimeError("Database unreachable")

    tool = build_podcast_rag_tool(mock_rag_service)
    sandbox = Sandbox(".")
    raw_output = tool.handler({"question": "Failing question"}, sandbox)

    data = json.loads(raw_output)
    assert "error" in data
    assert "Database unreachable" in data["error"]
    assert data["sources"] == []


# =============================================================================
# Input Validation & Error Handling Tests
# =============================================================================

@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_input", [
    "",
    "   ",
    "\n\t  ",
])
async def test_input_validation_empty(invalid_input: str):
    """Verifies that empty queries raise AgentValidationError."""
    agent = LennyAgent(provider=MockSDKProvider())
    with pytest.raises(AgentValidationError, match="non-empty string"):
        await agent.run(invalid_input)


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_input", [
    None,
    12345,
    {"query": "hello"},
])
async def test_input_validation_non_string(invalid_input: Any):
    """Verifies that non-string queries raise AgentValidationError."""
    agent = LennyAgent(provider=MockSDKProvider())
    with pytest.raises(AgentValidationError, match="non-empty string"):
        await agent.run(invalid_input)


@pytest.mark.asyncio
async def test_agent_execution_error_handling():
    """Verifies that unhandled SDK exceptions are caught and wrapped in AgentExecutionError."""
    class FailingProvider(LLMProvider):
        name = "failing"
        model = "failing-model"
        supports_streaming = False

        def complete(self, system: str, messages: List[NeutralMessage], tools: List[Dict[str, Any]]) -> AssistantResponse:
            raise RuntimeError("SDK Provider crashed unexpectedly")

    agent = LennyAgent(provider=FailingProvider())
    with pytest.raises(AgentExecutionError, match="Pi Coding Agent execution error"):
        await agent.run("Trigger failure")


# =============================================================================
# AgentResponse Schema Tests
# =============================================================================

def test_agent_response_schema():
    """Verifies AgentResponse serialization and schema attributes."""
    resp = AgentResponse(
        selected_tool="PodcastRAGTool",
        answer="Sample answer",
        sources=["Episode 1"]
    )
    assert resp.selected_tool == "PodcastRAGTool"
    assert resp.answer == "Sample answer"
    assert resp.sources == ["Episode 1"]

    dumped = resp.model_dump()
    assert dumped["selected_tool"] == "PodcastRAGTool"
    assert dumped["answer"] == "Sample answer"
    assert dumped["sources"] == ["Episode 1"]


# =============================================================================
# Upgraded Ship30Writer & Ship30Result Tests
# =============================================================================

def test_ship30_result_str_subclass_and_sources():
    """Verifies that Ship30Result functions as a string subclass with sources."""
    result = Ship30Result("Sample Essay Content", sources=["Episode 10 | Marty Cagan", "Episode 22 | Shreyas Doshi"])
    assert isinstance(result, str)
    assert result == "Sample Essay Content"
    assert result.essay == "Sample Essay Content"
    assert len(result) == len("Sample Essay Content")
    assert result.sources == ["Episode 10 | Marty Cagan", "Episode 22 | Shreyas Doshi"]


@pytest.mark.asyncio
async def test_ship30_writer_retrieval_grounding_and_sources():
    """Verifies that Ship30Writer queries the retriever when no context is passed and populates sources."""
    mock_retriever = AsyncMock()
    mock_retriever.retrieve.return_value = [
        RetrievalResult(
            chunk_id=1,
            content="Marty Cagan explains product discovery vs feature teams.",
            chunk_index=0,
            similarity_score=0.92,
            distance=0.08,
            episode_id=101,
            episode_title="Product management theater | Marty Cagan",
            episode_slug="marty-cagan",
            transcript_path=None
        ),
        RetrievalResult(
            chunk_id=2,
            content="Shreyas Doshi on high-agency product management.",
            chunk_index=1,
            similarity_score=0.88,
            distance=0.12,
            episode_id=102,
            episode_title="The art of product management | Shreyas Doshi",
            episode_slug="shreyas-doshi",
            transcript_path=None
        ),
    ]

    mock_llm = AsyncMock()
    mock_llm.generate.return_value = "Compelling long-form narrative essay discussing Marty Cagan and Shreyas Doshi."

    writer = Ship30Writer(llm_provider=mock_llm, retriever=mock_retriever)
    result = await writer.write("product strategy")

    assert isinstance(result, Ship30Result)
    assert "Marty Cagan" in result
    assert result.sources == [
        "Product management theater | Marty Cagan",
        "The art of product management | Shreyas Doshi"
    ]

    # Verify prompt passed to LLM enforced assignment constraints
    call_kwargs = mock_llm.generate.call_args.kwargs
    prompt = call_kwargs["prompt"]
    assert "### Structural Requirements:" in prompt
    assert "Target Word Count: Approximately 1,250 words" in prompt
    assert "The Hook (First 2-3 lines):" in prompt
    assert "Marty Cagan explains product discovery" in prompt


@pytest.mark.asyncio
async def test_ship30_writer_explicit_context_and_sources():
    """Verifies that Ship30Writer respects explicitly passed context and parses episode tags."""
    mock_llm = AsyncMock()
    mock_llm.generate.return_value = "Essay generated from user supplied context."

    mock_retriever = AsyncMock()
    writer = Ship30Writer(llm_provider=mock_llm, retriever=mock_retriever)

    custom_context = 'Episode: "The one question that saves product careers | Matt LeMay"\nMatt explains why questions matter.'
    result = await writer.write("asking questions", context=custom_context)

    assert result.startswith("Essay generated from user supplied context.")
    assert "## Sources" in result
    assert result.sources == ["The one question that saves product careers | Matt LeMay"]
    mock_retriever.retrieve.assert_not_called()


@pytest.mark.asyncio
async def test_ship30_writer_retrieval_fallback_graceful():
    """Verifies that Ship30Writer returns negative response without hallucination if retrieval fails."""
    mock_retriever = AsyncMock()
    mock_retriever.retrieve.side_effect = RuntimeError("Database connection timed out")

    mock_llm = AsyncMock()
    writer = Ship30Writer(llm_provider=mock_llm, retriever=mock_retriever)
    result = await writer.write("viral loops")

    assert result == "Not enough transcript evidence available."
    assert result.sources == []
    assert result.artifact is False
    mock_llm.generate.assert_not_called()


def test_ship30_tool_handler_with_sources():
    """Verifies that Ship30Tool handler extracts sources from Ship30Result."""
    mock_writer = AsyncMock()
    mock_writer.write.return_value = Ship30Result(
        "800-word authentic essay content",
        sources=["Episode 10 | Marty Cagan"]
    )

    tool = build_ship30_tool(mock_writer)
    sandbox = Sandbox(".")
    raw_output = tool.handler({"topic": "Product Strategy"}, sandbox)

    data = json.loads(raw_output)
    assert data["answer"] == "800-word authentic essay content"
    assert data["sources"] == ["Episode 10 | Marty Cagan"]


def test_ship30_tool_retrieval_and_context_passing():
    """Verifies that build_ship30_tool retrieves transcript chunks and passes context_data to writer."""
    mock_retriever = AsyncMock()
    mock_retriever.retrieve.return_value = [
        RetrievalResult(
            chunk_id=10,
            content="Anneka Gupta on product strategy at LiveRamp.",
            chunk_index=0,
            similarity_score=0.95,
            distance=0.05,
            episode_id=201,
            episode_title="Becoming more strategic | Anneka Gupta",
            episode_slug="anneka-gupta",
            transcript_path=None
        )
    ]

    mock_writer = AsyncMock()
    mock_writer.write.return_value = Ship30Result(
        "# Strategic Clarity\n\nDeep essay content...",
        sources=["Becoming more strategic | Anneka Gupta"]
    )

    tool = build_ship30_tool(writer=mock_writer, retriever=mock_retriever)
    sandbox = Sandbox(".")
    raw_output = tool.handler({"topic": "Product Strategy"}, sandbox)

    data = json.loads(raw_output)
    assert data["answer"] == "# Strategic Clarity\n\nDeep essay content..."
    assert data["sources"] == ["Becoming more strategic | Anneka Gupta"]

    # Verify writer was called with context_data containing retrieved transcript
    mock_writer.write.assert_called_once()
    call_kwargs = mock_writer.write.call_args.kwargs
    assert "Anneka Gupta on product strategy" in call_kwargs["context_data"]
    assert call_kwargs["user_query"] == "Product Strategy"


def test_ship30_tool_artifact_fields():
    """Verifies that Ship30Tool returns artifact=True, markdown_content, and html_content."""
    mock_writer = AsyncMock()
    mock_result = Ship30Result(
        "## Hook\nGreat hook\n\n## Sources\n- Episode 10",
        sources=["Episode 10"]
    )
    mock_result.markdown_content = "## Hook\nGreat hook\n\n## Sources\n- Episode 10"
    mock_result.html_content = "<h2>Hook</h2><p>Great hook</p>"
    mock_result.artifact = True
    mock_writer.write.return_value = mock_result

    tool = build_ship30_tool(writer=mock_writer)
    sandbox = Sandbox(".")
    raw_output = tool.handler({"topic": "Strategy"}, sandbox)

    data = json.loads(raw_output)
    assert data["artifact"] is True
    assert data["markdown_content"] == "## Hook\nGreat hook\n\n## Sources\n- Episode 10"
    assert "<h2" in data["html_content"]
    assert data["sources"] == ["Episode 10"]


def test_ship30_insufficient_evidence_handling():
    """Verifies that insufficient transcript evidence produces artifact=False and no hallucination."""
    mock_writer = AsyncMock()
    mock_result = Ship30Result("Not enough transcript evidence available.", sources=[])
    mock_result.markdown_content = None
    mock_result.html_content = None
    mock_result.artifact = False
    mock_writer.write.return_value = mock_result

    tool = build_ship30_tool(writer=mock_writer)
    sandbox = Sandbox(".")
    raw_output = tool.handler({"topic": "Unrelated topic"}, sandbox)

    data = json.loads(raw_output)
    assert data["answer"] == "Not enough transcript evidence available."
    assert data["artifact"] is False
    assert data["markdown_content"] is None
    assert data["html_content"] is None
    assert data["sources"] == []


@pytest.mark.asyncio
async def test_lenny_agent_ship30_artifact_routing():
    """Verifies that LennyAgent preserves artifact and HTML metadata from Ship30Tool."""
    mock_writer = AsyncMock()
    mock_result = Ship30Result(
        "# Strategic Stack\n\n## Hook\nHook text\n\n## Sources\n- Ravi Mehta",
        sources=["Ravi Mehta"]
    )
    mock_result.markdown_content = "# Strategic Stack\n\n## Hook\nHook text\n\n## Sources\n- Ravi Mehta"
    mock_result.html_content = "<h1>Strategic Stack</h1><h2>Hook</h2><p>Hook text</p>"
    mock_result.artifact = True
    mock_writer.write.return_value = mock_result

    mock_provider = MockSDKProvider(target_tool="Ship30Tool")
    custom_ship30_tool = build_ship30_tool(writer=mock_writer)
    agent = LennyAgent(provider=mock_provider, ship30_tool=custom_ship30_tool)

    response = await agent.run("Write a Ship30 article about product strategy stack")
    assert response.selected_tool == "Ship30Tool"
    assert response.artifact is True
    assert response.markdown_content is not None
    assert response.html_content is not None
    assert "Ravi Mehta" in response.sources


def test_ship30_section_targets_and_prompt_constraints():
    """Verifies that SECTION_TARGETS matches user word budget requirements."""
    assert SECTION_TARGETS["Hook"] == {"min": 150, "max": 200}
    assert SECTION_TARGETS["Problem"] == {"min": 200, "max": 250}
    assert SECTION_TARGETS["Insight"] == {"min": 250, "max": 300}
    assert SECTION_TARGETS["Lesson"] == {"min": 250, "max": 300}
    assert SECTION_TARGETS["Application"] == {"min": 250, "max": 300}
    assert SECTION_TARGETS["Conclusion"] == {"min": 100, "max": 150}

    # Verify prompt includes all required section targets and length
    assert "The Hook (First 2-3 lines): 150–200 words" in SHIP_30_PROMPT_TEMPLATE
    assert "Problem: 200–250 words" in SHIP_30_PROMPT_TEMPLATE
    assert "Insight: 250–300 words" in SHIP_30_PROMPT_TEMPLATE
    assert "Lesson: 250–300 words" in SHIP_30_PROMPT_TEMPLATE
    assert "Application: 250–300 words" in SHIP_30_PROMPT_TEMPLATE
    assert "Conclusion: 100–150 words" in SHIP_30_PROMPT_TEMPLATE
    assert "1,200 words" in SHIP_30_PROMPT_TEMPLATE


def test_count_words_and_markdown_section_parsers():
    """Verifies word counting and section splitting/reconstruction."""
    sample = "# Title\n\n## Hook\nWord one two three.\n\n## Problem\nWord four five six.\n\n## Sources\n- Source"
    assert count_words(sample) == 18
    assert count_words("") == 0

    sections = parse_markdown_sections(sample)
    assert len(sections) == 4
    assert sections[0][0] == "# Title"
    assert sections[1][0] == "## Hook"
    assert "Word one two three." in sections[1][1]

    reconstructed = reconstruct_markdown(sections)
    assert "# Title" in reconstructed
    assert "## Hook" in reconstructed
    assert "## Problem" in reconstructed


@pytest.mark.asyncio
async def test_ship30_writer_validation_triggers_auto_expansion():
    """Verifies that Ship30Writer expands under-target sections if initial draft is < 1200 words."""
    short_initial_draft = (
        "# Product Strategy Stack\n\n"
        "## Hook\nShort hook.\n\n"
        "## Problem\nShort problem.\n\n"
        "## Insight\nShort insight.\n\n"
        "## Lesson\nShort lesson.\n\n"
        "## Application\nShort application.\n\n"
        "## Action Steps\n1. Do this.\n\n"
        "## Conclusion\nShort conclusion.\n\n"
        "## Sources\n- Ravi Mehta"
    )

    expanded_section_text = " ".join(["in-depth framework tactical nuance analysis"] * 50)  # 250 words

    mock_llm = AsyncMock()
    # First call: initial short draft (<1200 words); subsequent calls: expanded section text
    mock_llm.generate.side_effect = [
        short_initial_draft,
        expanded_section_text,
        expanded_section_text,
        expanded_section_text,
        expanded_section_text,
    ]

    custom_context = 'Episode: "Product Strategy | Ravi Mehta"\nRavi explains strategy stack.'
    writer = Ship30Writer(llm_provider=mock_llm)
    result = await writer.write("product strategy", context=custom_context)

    # Verify that generate was called more than once (initial + expansions)
    assert mock_llm.generate.call_count > 1
    assert result.word_count > count_words(short_initial_draft)
    assert result.artifact is True


def test_ship30_tool_output_carries_word_count():
    """Verifies that Ship30Tool output JSON includes word_count."""
    mock_writer = AsyncMock()
    mock_result = Ship30Result(
        "# Essay\n\n## Hook\n" + ("word " * 1250) + "\n## Sources\n- Source",
        sources=["Episode 1"]
    )
    mock_writer.write.return_value = mock_result

    tool = build_ship30_tool(writer=mock_writer)
    sandbox = Sandbox(".")
    raw_output = tool.handler({"topic": "Strategy", "context": "Episode: 'Test'"}, sandbox)

    data = json.loads(raw_output)
    assert "word_count" in data
    assert data["word_count"] >= 1200


@pytest.mark.asyncio
async def test_lenny_agent_response_contains_word_count():
    """Verifies LennyAgent sets word_count on AgentResponse."""
    mock_writer = AsyncMock()
    mock_result = Ship30Result(
        "# Strategic Stack\n\n## Hook\n" + ("content " * 1210) + "\n## Sources\n- Ravi Mehta",
        sources=["Ravi Mehta"]
    )
    mock_writer.write.return_value = mock_result

    mock_provider = MockSDKProvider(target_tool="Ship30Tool")
    custom_ship30_tool = build_ship30_tool(writer=mock_writer)
    agent = LennyAgent(provider=mock_provider, ship30_tool=custom_ship30_tool)

    response = await agent.run("Write a Ship30 article about product strategy stack")
    assert response.selected_tool == "Ship30Tool"
    assert response.word_count is not None
    assert response.word_count >= 1200



