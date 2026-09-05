import logging
import re
from typing import List, Dict, Optional, Any
from app.providers.base import BaseLLMProvider
from app.providers.ollama_provider import OllamaProvider
from app.providers.provider_factory import get_provider

logger = logging.getLogger("query_rewriter")


class QueryRewriter:
    """
    Conversational query rewriter that resolves pronouns, ellipsis, and context-dependent
    references in follow-up queries using recent chat session history.
    """

    REWRITE_SYSTEM_PROMPT = (
        "You are a search query reformulation assistant. "
        "Your sole task is to rewrite a follow-up user question into a standalone, self-contained search query. "
        "Do NOT answer the question. Do NOT include explanations, quotes, or preambles. Output ONLY the rewritten question."
    )

    REWRITE_PROMPT_TEMPLATE = (
        "Given the conversation history and a follow-up question, rewrite the follow-up question into a single self-contained search query for a podcast transcript database.\n\n"
        "Guidelines:\n"
        "1. Resolve all ambiguous pronouns and coreferences (such as 'that framework', 'he', 'she', 'they', 'it', 'the model', 'that approach') using entities and topics from the conversation history.\n"
        "2. Explicitly retain and include any person/guest names (e.g. Ravi Mehta, Brian Chesky) and specific framework/topic names (e.g. Product Strategy Stack) mentioned in the conversation.\n"
        "3. If the follow-up question is already completely self-contained and clear without context, return it unchanged.\n"
        "4. Do NOT answer the question. Output ONLY the rewritten question text.\n\n"
        "Chat History:\n"
        "{history_str}\n\n"
        "Follow-up Question: {query}\n"
        "Rewritten Standalone Query:"
    )

    def __init__(self, llm_provider: Optional[BaseLLMProvider] = None):
        self._custom_llm_provider = llm_provider

    @property
    def llm_provider(self) -> BaseLLMProvider:
        if self._custom_llm_provider is not None:
            return self._custom_llm_provider
        return get_provider()

    @llm_provider.setter
    def llm_provider(self, val: Optional[BaseLLMProvider]) -> None:
        self._custom_llm_provider = val

    def format_history(self, chat_history: List[Dict[str, str]], max_messages: int = 6) -> str:
        """Formats the last N messages into a clean chronological transcript."""
        if not chat_history:
            return ""

        recent = chat_history[-max_messages:]
        lines = []
        for msg in recent:
            role = msg.get("role", "").capitalize() or "User"
            content = msg.get("content", "").strip()
            if content:
                # Truncate very long messages to avoid prompt bloat
                truncated = content if len(content) <= 300 else content[:300] + "..."
                lines.append(f"{role}: {truncated}")

        return "\n".join(lines)

    async def rewrite(self, query: str, chat_history: Optional[List[Dict[str, str]]] = None) -> str:
        """
        Rewrites a conversational follow-up question into a standalone search query.
        Returns the original query if history is empty or if rewriting is not required.
        """
        clean_query = query.strip()
        if not clean_query:
            return clean_query

        if not chat_history or len(chat_history) == 0:
            logger.info("Conversational Query Rewriting skipped (no history) | Original query: '%s'", clean_query)
            return clean_query

        history_str = self.format_history(chat_history)
        if not history_str.strip():
            logger.info("Conversational Query Rewriting skipped (empty history string) | Original query: '%s'", clean_query)
            return clean_query

        prompt = self.REWRITE_PROMPT_TEMPLATE.format(
            history_str=history_str,
            query=clean_query
        )

        try:
            raw_rewritten = await self.llm_provider.generate(
                prompt=prompt,
                system_prompt=self.REWRITE_SYSTEM_PROMPT,
                temperature=0.0
            )
            rewritten = raw_rewritten.strip()

            # Clean any wrapping quotes or accidental markdown
            rewritten = re.sub(r"^[\"']|[\"']$", "", rewritten).strip()
            if rewritten.lower().startswith("rewritten standalone query:"):
                rewritten = rewritten[len("rewritten standalone query:"):].strip()
            elif rewritten.lower().startswith("rewritten query:"):
                rewritten = rewritten[len("rewritten query:"):].strip()

            if not rewritten or len(rewritten) < 3:
                rewritten = clean_query

            logger.info(
                "Conversational Query Rewriting complete | Original query: '%s' | Rewritten query: '%s'",
                clean_query, rewritten
            )
            return rewritten

        except Exception as exc:
            logger.warning(
                "Query rewriting failed with error: %s. Falling back to original query: '%s'",
                exc, clean_query
            )
            return clean_query
