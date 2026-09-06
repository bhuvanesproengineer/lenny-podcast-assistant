import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.config import settings
from app.providers.ollama_provider import OllamaProvider
from app.providers.groq_provider import GroqProvider
from app.providers.provider_factory import (
    get_provider,
    set_active_provider_name,
    reset_active_provider_name,
)
from app.rag.embedding_router import (
    get_embedding_generator,
    set_active_embedding_provider,
    reset_active_embedding_provider,
    get_embedding_info,
    GeminiEmbeddingGenerator,
)
from app.rag.embeddings import EmbeddingGenerator
from app.rag.retriever import Retriever, RAGService
from app.main import run_startup_health_check


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def reset_overrides():
    yield
    reset_active_provider_name()
    reset_active_embedding_provider()


# =============================================================================
# 1. Provider Router Tests
# =============================================================================

def test_provider_router_ollama():
    set_active_provider_name("ollama")
    provider = get_provider()
    assert isinstance(provider, OllamaProvider)
    assert provider.provider_name == "ollama"


def test_provider_router_cloud():
    set_active_provider_name("cloud")
    provider = get_provider()
    assert isinstance(provider, GroqProvider)
    assert provider.provider_name == "groq"


# =============================================================================
# 2. Embedding Router Tests
# =============================================================================

def test_embedding_router_ollama():
    set_active_embedding_provider("ollama")
    generator = get_embedding_generator()
    assert isinstance(generator, EmbeddingGenerator)
    info = get_embedding_info()
    assert info["provider"] == "ollama"
    assert info["table"] == "transcript_chunks"
    assert info["model"] == "nomic-embed-text"


def test_embedding_router_gemini():
    set_active_embedding_provider("gemini")
    generator = get_embedding_generator()
    assert isinstance(generator, GeminiEmbeddingGenerator)
    info = get_embedding_info()
    assert info["provider"] == "gemini"
    assert info["table"] == "transcript_chunks_gemini"
    assert info["dimension"] == 768


def test_automatic_provider_routing_cloud():
    """When LLM_PROVIDER=cloud, embedding provider, vector table, and model must auto-route to cloud."""
    set_active_provider_name("cloud")
    # Reset embedding provider override to verify auto-routing from LLM provider
    reset_active_embedding_provider()

    generator = get_embedding_generator()
    assert isinstance(generator, GeminiEmbeddingGenerator)
    info = get_embedding_info()
    assert info["provider"] == "gemini"
    assert info["table"] == "transcript_chunks_gemini"
    assert info["model"] == "gemini-embedding-001"


def test_automatic_provider_routing_ollama():
    """When LLM_PROVIDER=ollama, embedding provider, vector table, and model must auto-route to ollama."""
    set_active_provider_name("ollama")
    reset_active_embedding_provider()

    generator = get_embedding_generator()
    assert isinstance(generator, EmbeddingGenerator)
    info = get_embedding_info()
    assert info["provider"] == "ollama"
    assert info["table"] == "transcript_chunks"
    assert info["model"] == "nomic-embed-text"


# =============================================================================
# 3. Database Routing & Isolation Tests
# =============================================================================

@pytest.mark.anyio
async def test_retriever_database_routing_local():
    set_active_provider_name("ollama")
    set_active_embedding_provider("ollama")

    mock_generator = MagicMock()
    mock_generator.get_single_embedding = AsyncMock(return_value=[0.05] * 768)

    mock_session = AsyncMock()
    mock_result = MagicMock()
    # Mock row: (TranscriptChunk, Episode, distance)
    mock_chunk = MagicMock()
    mock_chunk.id = 1
    mock_chunk.content = "Local content"
    mock_chunk.chunk_index = 0
    mock_ep = MagicMock()
    mock_ep.id = 1
    mock_ep.title = "Local Episode"
    mock_ep.slug = "local-episode"
    mock_ep.transcript_path = None
    mock_result.all.return_value = [(mock_chunk, mock_ep, 0.2)]
    mock_session.execute.return_value = mock_result

    retriever = Retriever(embedding_generator=mock_generator)
    results = await retriever.retrieve("local query", session=mock_session)

    assert len(results) == 1
    assert results[0].content == "Local content"
    assert results[0].episode_title == "Local Episode"

    # Verify query executed against transcript_chunks / Episode join
    mock_session.execute.assert_awaited_once()
    sql_stmt = str(mock_session.execute.call_args[0][0])
    assert "transcript_chunks" in sql_stmt
    assert "transcript_chunks_gemini" not in sql_stmt


@pytest.mark.anyio
async def test_retriever_database_routing_cloud():
    set_active_provider_name("cloud")
    set_active_embedding_provider("gemini")

    mock_generator = MagicMock()
    mock_generator.provider = "gemini"
    mock_generator.get_single_embedding = AsyncMock(return_value=[0.05] * 768)

    mock_session = AsyncMock()
    mock_result = MagicMock()
    # Mock row: (TranscriptChunkGemini, distance)
    mock_gemini_chunk = MagicMock()
    mock_gemini_chunk.id = "c3f2d212-0000-0000-0000-000000000001"
    mock_gemini_chunk.chunk_text = "Cloud Gemini content"
    mock_gemini_chunk.episode_title = "Cloud Episode"
    mock_gemini_chunk.guest_name = "Cloud Guest"
    mock_gemini_chunk.youtube_url = "https://youtube.com/watch?v=123"
    mock_result.all.return_value = [(mock_gemini_chunk, 0.15)]
    mock_session.execute.return_value = mock_result

    retriever = Retriever(embedding_generator=mock_generator)
    results = await retriever.retrieve("cloud query", session=mock_session)

    assert len(results) == 1
    assert results[0].content == "Cloud Gemini content"
    assert results[0].episode_title == "Cloud Episode"
    assert results[0].similarity_score == 0.85

    # Verify query executed against transcript_chunks_gemini ONLY
    mock_session.execute.assert_awaited_once()
    sql_stmt = str(mock_session.execute.call_args[0][0])
    assert "transcript_chunks_gemini" in sql_stmt


# =============================================================================
# 4. Strict Cloud Validation (Zero Ollama / Localhost dependencies)
# =============================================================================

@pytest.mark.anyio
async def test_strict_cloud_validation_no_ollama_dependencies():
    """
    Validates that in Cloud mode (LLM_PROVIDER=cloud, EMBEDDING_PROVIDER=gemini):
    - No calls to localhost:11434
    - No calls to Ollama APIs
    - No queries to transcript_chunks
    - Everything routes through Groq + Gemini + transcript_chunks_gemini
    """
    set_active_provider_name("cloud")
    set_active_embedding_provider("gemini")

    service = RAGService()
    assert isinstance(service.llm_provider, GroqProvider)
    assert isinstance(service.retriever.embedding_generator, GeminiEmbeddingGenerator)

    # Intercept any HTTP calls and verify NO localhost:11434 calls are ever made
    with patch("httpx.AsyncClient.post") as mock_http_post:
        # Mock Gemini embed response on the class
        with patch.object(
            GeminiEmbeddingGenerator,
            "get_single_embedding",
            new_callable=AsyncMock
        ) as mock_embed:
            mock_embed.return_value = [0.01] * 768

            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_chunk = MagicMock()
            mock_chunk.id = "c3f2d212-0000-0000-0000-000000000002"
            mock_chunk.chunk_text = "Insights from Lenny's guest on product-led growth."
            mock_chunk.episode_title = "Product-Led Growth Masterclass"
            mock_chunk.guest_name = "Elena Verna"
            mock_chunk2 = MagicMock()
            mock_chunk2.id = "c3f2d212-0000-0000-0000-000000000003"
            mock_chunk2.chunk_text = "Self-serve loops are essential for scale."
            mock_chunk2.episode_title = "Product-Led Growth Masterclass"
            mock_chunk2.guest_name = "Elena Verna"
            mock_chunk2.youtube_url = "https://youtube.com/watch?v=elena"
            mock_result.all.return_value = [(mock_chunk, 0.2), (mock_chunk2, 0.22)]
            mock_session.execute.return_value = mock_result

            # Mock GroqProvider methods on the class so any instance created uses mock
            with patch.object(
                GroqProvider,
                "generate_response",
                new_callable=AsyncMock
            ) as mock_llm_gen, patch.object(
                GroqProvider,
                "generate",
                new_callable=AsyncMock
            ) as mock_llm_gen2:
                mock_llm_gen.return_value = "Elena Verna recommends focusing on self-serve acquisition."
                mock_llm_gen2.return_value = "Elena Verna recommends focusing on self-serve acquisition."

                response = await service.answer("How to optimize PLG?", session=mock_session)

                # Check answer and sources
                assert "Elena Verna" in response.answer
                assert response.sources == ["Product-Led Growth Masterclass"]

                # Assert that the SQL query executed was ONLY on transcript_chunks_gemini
                executed_sql = str(mock_session.execute.call_args[0][0])
                assert "transcript_chunks_gemini" in executed_sql
                assert "transcript_chunks " not in executed_sql

                # Verify no HTTP calls went to localhost:11434
                for call in mock_http_post.call_args_list:
                    url = str(call[0][0]) if call[0] else ""
                    assert "localhost:11434" not in url
                    assert "11434" not in url


@pytest.mark.anyio
async def test_retriever_selected_logging_cloud_output(capsys):
    """Verifies that retrieval prints the exact Selected fields required by prompt."""
    set_active_provider_name("cloud")
    reset_active_embedding_provider()

    service = RAGService()
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_chunk = MagicMock()
    mock_chunk.id = "c3f2d212-0000-0000-0000-000000000002"
    mock_chunk.chunk_text = "Content."
    mock_chunk.episode_title = "Episode Title"
    mock_chunk.guest_name = "Guest Name"
    mock_chunk.youtube_url = "https://youtube.com"
    mock_result.all.return_value = [(mock_chunk, 0.2)]
    mock_session.execute.return_value = mock_result

    with patch.object(
        GeminiEmbeddingGenerator,
        "get_single_embedding",
        new_callable=AsyncMock
    ) as mock_embed:
        mock_embed.return_value = [0.01] * 768
        await service.retriever.retrieve("growth loops", session=mock_session)

    captured = capsys.readouterr().out
    assert "Selected LLM Provider: cloud" in captured
    assert "Selected Embedding Provider: gemini" in captured
    assert "Selected Vector Table: transcript_chunks_gemini" in captured
    assert "Selected Chat Model: openai/gpt-oss-20b" in captured
    assert "Selected Embedding Model: gemini-embedding-001" in captured


# =============================================================================
# 5. Startup Health Check Test
# =============================================================================

@pytest.mark.anyio
async def test_startup_health_check_output(capsys):
    set_active_provider_name("cloud")
    set_active_embedding_provider("gemini")

    await run_startup_health_check()
    captured = capsys.readouterr().out

    assert "STARTUP HEALTH CHECK" in captured
    assert "Selected Embedding Provider: gemini" in captured
    assert "Selected Embedding Model: gemini-embedding-001" in captured
    assert "Current LLM Provider:          cloud" in captured
    assert "Current Embedding Provider:    gemini" in captured
    assert "Current Vector Table:          transcript_chunks_gemini" in captured
    assert "Chunk Count In Selected Table:" in captured


@pytest.mark.anyio
async def test_gemini_verify_embedding_model_and_test_embedding():
    """Verifies startup model existence check and 'hello world' test embedding generation."""
    gen = GeminiEmbeddingGenerator()
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_item = MagicMock()
    mock_item.values = [0.01] * 768
    mock_resp.embeddings = [mock_item]
    mock_client.models.get.return_value = MagicMock(name="models/gemini-embedding-001")
    mock_client.models.embed_content.return_value = mock_resp

    with patch.object(gen, "_get_client", return_value=mock_client):
        res = await gen.verify_embedding_model_exists()
        assert res["exists"] is True
        assert res["tested"] is True
        assert res["dimension"] == 768
        assert res["model"] == "gemini-embedding-001"


@pytest.mark.anyio
async def test_gemini_embedding_failure_logging(capsys):
    """Verifies that on Gemini embedding failure, exact model name, endpoint, and response body are logged."""
    gen = GeminiEmbeddingGenerator()
    mock_client = MagicMock()
    mock_client.models.embed_content.side_effect = RuntimeError("Custom API 404 error details")

    with patch.object(gen, "_get_client", return_value=mock_client):
        with pytest.raises(RuntimeError):
            await gen.get_embeddings(["sample query"])

    captured = capsys.readouterr().out
    assert "Exact Model Name: gemini-embedding-001" in captured
    assert "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent" in captured
    assert "Response Body: Custom API 404 error details" in captured


# =============================================================================
# 6. Cloud Mode Token Budget & Top-K Controls Tests
# =============================================================================

@pytest.mark.anyio
async def test_cloud_mode_top_k_reduction():
    from app.agent.tools import build_podcast_rag_tool
    from app.rag.retriever import RAGService
    from pi_agent.tools.base import Sandbox

    set_active_provider_name("cloud")
    set_active_embedding_provider("gemini")

    mock_service = MagicMock(spec=RAGService)
    mock_service.answer = AsyncMock(return_value=MagicMock(answer="Cloud Answer", sources=["Episode 1"]))

    tool = build_podcast_rag_tool(rag_service=mock_service)
    # Execute without specifying top_k
    tool.handler({"question": "What is growth?"}, Sandbox("."))

    # In Cloud mode, top_k defaults to 4 (reduced from 6)
    mock_service.answer.assert_awaited_once()
    assert mock_service.answer.call_args.kwargs["top_k"] == 4


@pytest.mark.anyio
async def test_local_mode_top_k_untouched():
    from app.agent.tools import build_podcast_rag_tool
    from app.rag.retriever import RAGService
    from pi_agent.tools.base import Sandbox

    set_active_provider_name("ollama")
    set_active_embedding_provider("ollama")

    mock_service = MagicMock(spec=RAGService)
    mock_service.answer = AsyncMock(return_value=MagicMock(answer="Local Answer", sources=["Episode 1"]))

    tool = build_podcast_rag_tool(rag_service=mock_service)
    tool.handler({"question": "What is growth?"}, Sandbox("."))

    # In Local Ollama mode, top_k remains 6 (strictly untouched)
    mock_service.answer.assert_awaited_once()
    assert mock_service.answer.call_args.kwargs["top_k"] == 6


def test_context_compression_and_trimming():
    from app.rag.cloud_optimizations import (
        compress_transcript_content,
        build_cloud_context,
        estimate_tokens
    )
    from app.rag.retriever import RetrievalResult

    raw = "Hello   world!\n\n\n\nThis  is   a   test.\n\n\n\nExtra lines."
    compressed = compress_transcript_content(raw)
    assert "\n\n\n" not in compressed
    assert "   " not in compressed

    chunks = [
        RetrievalResult(
            chunk_id=i,
            content=f"Content for excerpt {i}. " + ("Informative text about product strategy and metrics. " * 30),
            chunk_index=0,
            similarity_score=0.8,
            distance=0.2,
            episode_id=i,
            episode_title=f"Episode {i}",
            episode_slug="",
            transcript_path=""
        )
        for i in range(1, 6)
    ]

    # With a budget of 300 tokens, it should trim and retain fewer chunks
    context_str, retained = build_cloud_context(chunks, max_tokens=300)
    assert len(retained) < 5
    assert estimate_tokens(context_str) <= 350


@pytest.mark.anyio
async def test_tpm_protection_tracker():
    from app.rag.cloud_optimizations import TPMTracker

    tracker = TPMTracker(tpm_limit=500)
    # Acquire 300 tokens: should succeed immediately
    sleep1 = await tracker.acquire(300)
    assert sleep1 == 0.0
    assert tracker.get_current_window_tokens() == 300

