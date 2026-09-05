import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.rag.retriever import Retriever, RetrievalResult, RAGService, RAGResponse
from app.models.db_models import Episode, TranscriptChunk

@pytest.fixture
def anyio_backend():
    return "asyncio"

@pytest.mark.anyio
async def test_retriever_empty_query():
    retriever = Retriever()
    results = await retriever.retrieve(query="   ")
    assert results == []

@pytest.mark.anyio
async def test_retriever_mocked_search():
    mock_generator = MagicMock()
    mock_generator.get_single_embedding = AsyncMock(return_value=[0.1] * 768)

    mock_episode = Episode(
        id=42,
        title="Scaling Startups",
        slug="scaling-startups",
        transcript_path="/path/to/transcript.md"
    )
    mock_chunk = TranscriptChunk(
        id=101,
        episode_id=42,
        chunk_index=3,
        content="This is an insightful growth tip.",
        embedding=[0.1] * 768
    )

    mock_session = AsyncMock()
    mock_result = MagicMock()
    # Mock row returns: (chunk, episode, distance)
    # distance = 0.25 -> similarity = 0.75
    mock_result.all.return_value = [(mock_chunk, mock_episode, 0.25)]
    mock_session.execute.return_value = mock_result

    retriever = Retriever(embedding_generator=mock_generator, default_top_k=5)
    results = await retriever.retrieve(query="growth tips", session=mock_session)

    assert len(results) == 1
    res = results[0]
    assert isinstance(res, RetrievalResult)
    assert res.chunk_id == 101
    assert res.episode_id == 42
    assert res.episode_title == "Scaling Startups"
    assert res.episode_slug == "scaling-startups"
    assert res.similarity_score == 0.75
    assert res.distance == 0.25
    assert "growth tip" in res.content

@pytest.mark.anyio
async def test_retriever_embedding_failure():
    mock_generator = MagicMock()
    mock_generator.get_single_embedding = AsyncMock(side_effect=Exception("Ollama connection failed"))

    retriever = Retriever(embedding_generator=mock_generator)
    with pytest.raises(RuntimeError, match="Query embedding generation failed"):
        await retriever.retrieve(query="failing query")

@pytest.mark.anyio
async def test_rag_service_answer():
    mock_retriever = MagicMock()
    mock_chunk = RetrievalResult(
        chunk_id=1,
        content="Focus on retained users first before scaling top of funnel.",
        chunk_index=0,
        similarity_score=0.88,
        distance=0.12,
        episode_id=10,
        episode_title="Retention Mastery with Casey Winters",
        episode_slug="casey-winters",
        transcript_path=None
    )
    mock_retriever.retrieve = AsyncMock(return_value=[mock_chunk])

    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(
        return_value="According to Casey Winters, you should focus on retaining users first before scaling acquisition."
    )

    service = RAGService(retriever=mock_retriever, llm_provider=mock_llm)
    response = await service.answer("How to prioritize retention?")

    assert isinstance(response, RAGResponse)
    assert "Casey Winters" in response.answer
    assert response.sources == ["Retention Mastery with Casey Winters"]
    assert len(response.retrieved_chunks) == 1
    assert response.retrieved_chunks[0].chunk_id == 1
