import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.rag.retriever import Retriever, RetrievalResult, RAGService, RAGResponse
from app.models.db_models import Episode, TranscriptChunk

from app.providers.provider_factory import reset_active_provider_name
from app.rag.embedding_router import reset_active_embedding_provider

@pytest.fixture
def anyio_backend():
    return "asyncio"

@pytest.fixture(autouse=True)
def cleanup_overrides():
    reset_active_provider_name()
    reset_active_embedding_provider()
    yield
    reset_active_provider_name()
    reset_active_embedding_provider()

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
    mock_chunk1 = RetrievalResult(
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
    mock_chunk2 = RetrievalResult(
        chunk_id=2,
        content="Retention is the foundation of growth loops.",
        chunk_index=1,
        similarity_score=0.85,
        distance=0.15,
        episode_id=10,
        episode_title="Retention Mastery with Casey Winters",
        episode_slug="casey-winters",
        transcript_path=None
    )
    mock_retriever.retrieve = AsyncMock(return_value=[mock_chunk1, mock_chunk2])

    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(
        return_value=(
            "## Answer\n\n"
            "According to Casey Winters, you should focus on retaining users first before scaling acquisition [Source: Casey Winters, Retention Mastery with Casey Winters].\n\n"
            "## Key Insights\n\n"
            "- Prioritize retention before acquisition\n"
            "- Retention fuels loops\n\n"
            "## Sources\n\n"
            "Episode: Retention Mastery with Casey Winters\n"
            "Guest: Casey Winters\n"
            "Timestamp: N/A"
        )
    )

    service = RAGService(retriever=mock_retriever, llm_provider=mock_llm)
    response = await service.answer("How to prioritize retention?")

    assert isinstance(response, RAGResponse)
    assert "Casey Winters" in response.answer
    assert "## Answer" in response.answer
    assert "## Key Insights" in response.answer
    assert "## Sources" in response.answer
    assert response.sources == ["Retention Mastery with Casey Winters"]
    assert len(response.retrieved_chunks) == 2
    assert response.retrieved_chunks[0].chunk_id == 1


@pytest.mark.anyio
async def test_rag_service_fewer_than_2_chunks_refusal():
    """Verifies that retrieval with fewer than 2 relevant chunks is refused."""
    mock_retriever = MagicMock()
    mock_chunk = RetrievalResult(
        chunk_id=1,
        content="Single chunk only.",
        chunk_index=0,
        similarity_score=0.90,
        distance=0.10,
        episode_id=1,
        episode_title="Lenny Episode",
        episode_slug="lenny-episode",
        transcript_path=None
    )
    # Only 1 chunk (< 2 chunks required)
    mock_retriever.retrieve = AsyncMock(return_value=[mock_chunk])

    mock_llm = MagicMock()
    service = RAGService(retriever=mock_retriever, llm_provider=mock_llm)
    response = await service.answer("What is the retention strategy?")

    assert "Not enough transcript evidence available" in response.answer
    assert response.sources == []
    mock_llm.generate.assert_not_called()


@pytest.mark.anyio
async def test_rag_service_low_similarity_refusal():
    """Verifies that chunks below similarity threshold trigger a refusal."""
    mock_retriever = MagicMock()
    c1 = RetrievalResult(
        chunk_id=1, content="Irrelevant content 1", chunk_index=0,
        similarity_score=0.20, distance=0.80, episode_id=1,
        episode_title="Ep 1", episode_slug="ep-1", transcript_path=None
    )
    c2 = RetrievalResult(
        chunk_id=2, content="Irrelevant content 2", chunk_index=1,
        similarity_score=0.25, distance=0.75, episode_id=1,
        episode_title="Ep 1", episode_slug="ep-1", transcript_path=None
    )
    mock_retriever.retrieve = AsyncMock(return_value=[c1, c2])

    mock_llm = MagicMock()
    service = RAGService(retriever=mock_retriever, llm_provider=mock_llm)
    response = await service.answer("What is the sourdough recipe?")

    assert "Not enough transcript evidence available" in response.answer
    assert response.sources == []
    mock_llm.generate.assert_not_called()


@pytest.mark.anyio
async def test_embedding_generator_404_fallback_to_legacy_embeddings():
    """Verifies that EmbeddingGenerator falls back to /api/embeddings if /api/embed returns 404."""
    from app.rag.embeddings import EmbeddingGenerator
    import httpx

    gen = EmbeddingGenerator(base_url="http://mock-ollama:11434", model="nomic-embed-text")

    # Mock client and post responses
    mock_client = AsyncMock()

    def mock_post(url, json=None):
        mock_resp = MagicMock()
        if url.endswith("/api/embed"):
            mock_resp.status_code = 404
            mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError("404 Not Found", request=MagicMock(), response=mock_resp)
        elif url.endswith("/api/embeddings"):
            mock_resp.status_code = 200
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {"embedding": [0.5] * 768}
        return mock_resp

    mock_client.post = AsyncMock(side_effect=mock_post)
    mock_client.is_closed = False
    gen.get_client = AsyncMock(return_value=mock_client)

    # Test batch call
    embeddings = await gen.get_embeddings(["How to prioritize retention?"])
    assert len(embeddings) == 1
    assert len(embeddings[0]) == 768
    assert gen._use_legacy_endpoint is True

    # Test single embedding call in legacy mode
    single_emb = await gen.get_single_embedding("Growth loops")
    assert len(single_emb) == 768

