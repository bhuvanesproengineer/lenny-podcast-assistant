import pytest
from unittest.mock import AsyncMock, MagicMock

from app.rag.query_rewriter import QueryRewriter
from app.rag.retriever import find_matching_episode_ids, is_boilerplate
from app.agent.agent import LennyAgent
from pi_agent.llm import LLMProvider, AssistantResponse, ToolCall


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_query_rewriter_no_history():
    rewriter = QueryRewriter()
    q = "What did Ravi Mehta say about product strategy?"
    res = await rewriter.rewrite(q, chat_history=None)
    assert res == q

    res2 = await rewriter.rewrite(q, chat_history=[])
    assert res2 == q


@pytest.mark.anyio
async def test_query_rewriter_resolves_pronouns():
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(
        return_value="Tell me more about Ravi Mehta's Product Strategy Stack framework."
    )
    rewriter = QueryRewriter(llm_provider=mock_llm)

    history = [
        {"role": "user", "content": "What did Ravi Mehta say about product strategy?"},
        {"role": "assistant", "content": "Ravi Mehta introduced the Product Strategy Stack framework."}
    ]

    rewritten = await rewriter.rewrite("Tell me more about that framework.", chat_history=history)

    assert rewritten == "Tell me more about Ravi Mehta's Product Strategy Stack framework."
    assert mock_llm.generate.called
    call_kwargs = mock_llm.generate.call_args[1]
    prompt_sent = call_kwargs.get("prompt", "")
    assert "What did Ravi Mehta say" in prompt_sent
    assert "Tell me more about that framework." in prompt_sent


@pytest.mark.anyio
async def test_query_rewriter_exception_fallback():
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(side_effect=RuntimeError("Ollama timeout"))
    rewriter = QueryRewriter(llm_provider=mock_llm)

    history = [{"role": "user", "content": "Who is Ravi Mehta?"}]
    q = "Tell me more about him."
    # Should not raise; should safely fallback to original query
    res = await rewriter.rewrite(q, chat_history=history)
    assert res == q


def test_speaker_matching_find_matching_episode_ids():
    episodes = [
        {"id": 250, "title": "How to build your product strategy stack | Ravi Mehta", "slug": "ravi-mehta"},
        {"id": 100, "title": "Designing Product | Brian Chesky", "slug": "brian-chesky"},
        {"id": 15, "title": "Growth Systems | Elena Verna", "slug": "elena-verna"},
    ]

    # Exact slug match
    matched = find_matching_episode_ids("What did Ravi Mehta say about product strategy?", episodes)
    assert matched == [250]

    # Partial / lowercase match
    matched2 = find_matching_episode_ids("Can you explain Brian Chesky's thoughts?", episodes)
    assert matched2 == [100]

    # No match
    matched3 = find_matching_episode_ids("How to calculate customer acquisition cost?", episodes)
    assert matched3 == []


def test_boilerplate_filter():
    # Empty title header chunk
    header_chunk = "# How to build your product strategy stack | Ravi Mehta\n\n## Transcript"
    assert is_boilerplate(header_chunk) is True

    # Outro boilerplate chunk
    outro_chunk = "Listen to Lenny's Podcast on your favorite podcast app. Please leave a rating and review!"
    assert is_boilerplate(outro_chunk) is True

    # Substantive content chunk
    real_chunk = (
        "Ravi Mehta (00:18:43): The goal of the product strategy stack is to help people "
        "take a set of terms that are normally conflated together, like goals, roadmap, strategy, "
        "and separate them into clearly defined parts."
    )
    assert is_boilerplate(real_chunk) is False


@pytest.mark.anyio
async def test_agent_run_with_chat_history():
    class DummyProvider(LLMProvider):
        name = "dummy"
        model = "dummy-model"
        supports_streaming = False

        def complete(self, system, messages, tools):
            last_msg = messages[-1].get("content", "")
            return AssistantResponse(
                text=f"Processed: {last_msg}",
                tool_calls=[]
            )

    mock_rewriter = MagicMock()
    mock_rewriter.rewrite = AsyncMock(
        return_value="Tell me more about Ravi Mehta's Product Strategy Stack framework."
    )

    agent = LennyAgent(provider=DummyProvider(), query_rewriter=mock_rewriter)
    history = [
        {"role": "user", "content": "What did Ravi Mehta say about product strategy?"}
    ]

    res = await agent.run("Tell me more about that framework.", chat_history=history)

    assert mock_rewriter.rewrite.called
    assert "Tell me more about Ravi Mehta's Product Strategy Stack framework." in res.answer
