import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from app.providers.base import BaseLLMProvider
from app.providers.ollama_provider import OllamaProvider
from app.providers.cloud_provider import CloudProvider
from app.skills.artifact_generator import ArtifactGenerator, ArtifactType, GeneratedArtifact


from app.providers.provider_factory import reset_active_provider_name


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def cleanup_provider_override():
    yield
    reset_active_provider_name()


def test_base_provider_abstract():
    with pytest.raises(TypeError):
        BaseLLMProvider()


@pytest.mark.anyio
async def test_ollama_provider_generate_success():
    provider = OllamaProvider(base_url="http://mock-ollama:11434", model="llama3.2:3b")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"response": "Mocked Ollama response text"}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        result = await provider.generate(
            prompt="Hello world",
            system_prompt="You are a helpful assistant",
            temperature=0.7,
        )

        assert result == "Mocked Ollama response text"
        mock_post.assert_awaited_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "http://mock-ollama:11434/api/generate"
        assert kwargs["json"]["model"] == "llama3.2:3b"
        assert kwargs["json"]["prompt"] == "Hello world"
        assert kwargs["json"]["system"] == "You are a helpful assistant"
        assert kwargs["json"]["options"]["temperature"] == 0.7


@pytest.mark.anyio
async def test_ollama_provider_generate_error():
    provider = OllamaProvider(base_url="http://mock-ollama:11434")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.ConnectError("Connection refused")

        with pytest.raises(RuntimeError, match="Ollama generation error"):
            await provider.generate("Test prompt")


@pytest.mark.anyio
async def test_cloud_provider_generate_success():
    provider = CloudProvider(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        model="gpt-4o"
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "choices": [
            {"message": {"role": "assistant", "content": "Cloud answer from GPT-4o"}}
        ]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        result = await provider.generate(
            prompt="What is retention?",
            system_prompt="Be concise",
            temperature=0.1,
        )

        assert result == "Cloud answer from GPT-4o"
        mock_post.assert_awaited_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://api.openai.com/v1/chat/completions"
        assert kwargs["headers"]["Authorization"] == "Bearer test-key"
        assert kwargs["json"]["model"] == "gpt-4o"
        assert kwargs["json"]["messages"][0] == {"role": "system", "content": "Be concise"}
        assert kwargs["json"]["messages"][1] == {"role": "user", "content": "What is retention?"}


@pytest.mark.anyio
async def test_cloud_provider_generate_error():
    provider = CloudProvider(api_key="bad-key")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.HTTPStatusError("401 Unauthorized", request=MagicMock(), response=MagicMock())

        with pytest.raises(RuntimeError, match="Cloud generation error"):
            await provider.generate("Hello")


def test_artifact_generator_utilities():
    raw_markdown = "# How to Find Product-Market Fit\n\nPMF is essential for growth.\nKeep talking to users."
    title = ArtifactGenerator.extract_title(raw_markdown)
    assert title == "How to Find Product-Market Fit"

    default_title = ArtifactGenerator.extract_title("No header here, just text.")
    assert default_title == "Artifact Document"

    sources = ["Episode 1 - PMF", "Episode 2 - Metrics"]
    sources_section = ArtifactGenerator.format_sources_section(sources)
    assert "## Sources" in sources_section
    assert "- Episode 1 - PMF" in sources_section

    artifact = ArtifactGenerator.create_artifact(
        content=raw_markdown,
        artifact_type=ArtifactType.ESSAY,
        sources=sources,
    )
    assert artifact.title == "How to Find Product-Market Fit"
    assert artifact.artifact_type == ArtifactType.ESSAY
    assert artifact.word_count > 0
    assert len(artifact.sources) == 2


@pytest.mark.anyio
async def test_common_interface_generate_response_and_ship30():
    from app.providers.ollama_provider import OllamaProvider
    from app.providers.cloud_provider import CloudProvider

    # Test OllamaProvider common interface
    ollama = OllamaProvider(base_url="http://mock-ollama:11434")
    with patch.object(ollama, "generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = "Generated response text"
        resp = await ollama.generate_response("Question prompt")
        assert resp == "Generated response text"
        mock_gen.assert_awaited_once()

    with patch.object(ollama, "generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = "# Growth Hook\n## Problem\nContent"
        article = await ollama.generate_ship30_article("Growth loops")
        assert "Growth Hook" in article
        mock_gen.assert_awaited_once()

    # Test CloudProvider common interface
    cloud = CloudProvider(api_key="mock-key")
    with patch.object(cloud, "generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = "Cloud response"
        resp = await cloud.generate_response("Question prompt")
        assert resp == "Cloud response"

    with patch.object(cloud, "generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = "# Cloud Article\n## Hook\nContent"
        article = await cloud.generate_ship30_article("Retention")
        assert "Cloud Article" in article


def test_provider_factory_and_fallback():
    from app.providers.provider_factory import (
        get_provider,
        get_active_provider_name,
        set_active_provider_name,
        get_provider_status,
        _runtime_provider_override,
    )

    # Set and get active provider name
    set_active_provider_name("ollama")
    assert get_active_provider_name() == "ollama"

    ollama_p = get_provider("ollama")
    assert ollama_p.provider_name == "ollama"
    assert ollama_p.is_local is True

    # Switching to cloud with no API key should fall back to Ollama gracefully
    with patch.dict("os.environ", {}, clear=True):
        with patch("app.config.settings.OPENROUTER_API_KEY", ""):
            with patch("app.config.settings.OPENAI_API_KEY", ""):
                with patch("app.config.settings.GROQ_API_KEY", ""):
                    with patch("app.config.settings.FALLBACK_TO_LOCAL", True):
                        fallback_p = get_provider("cloud", fallback_on_error=True)
                        assert fallback_p.provider_name == "ollama"

    # Switching to cloud with API key succeeds
    with patch.dict("os.environ", {"OPENROUTER_API_KEY": "sk-or-v1-test"}):
        cloud_p = get_provider("cloud", fallback_on_error=False)
        assert cloud_p.provider_name == "cloud"
        assert cloud_p.is_local is False

    # Status diagnostic dictionary
    status = get_provider_status()
    assert "active_provider" in status
    assert "local" in status
    assert "cloud" in status
    assert "fallback_enabled" in status


@pytest.mark.anyio
async def test_groq_provider_generate_success():
    from app.providers.groq_provider import GroqProvider

    provider = GroqProvider(
        api_key="gsk-mock-key",
        base_url="https://api.groq.com/openai/v1",
        model="openai/gpt-oss-20b"
    )
    assert provider.provider_name == "groq"
    assert provider.model_name == "openai/gpt-oss-20b"
    assert provider.is_local is False
    assert provider.is_configured() is True

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "choices": [
            {"message": {"role": "assistant", "content": "Groq response text"}}
        ]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        result = await provider.generate(
            prompt="What is product growth?",
            system_prompt="Be concise",
            temperature=0.2,
        )

        assert result == "Groq response text"
        mock_post.assert_awaited_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://api.groq.com/openai/v1/chat/completions"
        assert kwargs["headers"]["Authorization"] == "Bearer gsk-mock-key"
        assert kwargs["json"]["model"] == "openai/gpt-oss-20b"
        assert kwargs["json"]["messages"][0] == {"role": "system", "content": "Be concise"}
        assert kwargs["json"]["messages"][1] == {"role": "user", "content": "What is product growth?"}


@pytest.mark.anyio
async def test_groq_provider_generate_error():
    from app.providers.groq_provider import GroqProvider

    provider = GroqProvider(api_key="bad-groq-key")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.HTTPStatusError("401 Unauthorized", request=MagicMock(), response=MagicMock())

        with pytest.raises(RuntimeError, match="Groq generation error"):
            await provider.generate("Hello Groq")


@pytest.mark.anyio
async def test_groq_provider_common_interface():
    from app.providers.groq_provider import GroqProvider

    groq = GroqProvider(api_key="gsk-test")
    with patch.object(groq, "generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = "Grounded Groq Answer"
        resp = await groq.generate_response("User question")
        assert resp == "Grounded Groq Answer"
        mock_gen.assert_awaited_once()

    with patch.object(groq, "generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = "# Ship30 Title\n## Hook\nContent"
        article = await groq.generate_ship30_article("Retention Loops")
        assert "Ship30 Title" in article
        mock_gen.assert_awaited_once()


def test_provider_factory_groq_routing():
    from app.providers.provider_factory import (
        get_provider,
        set_active_provider_name,
        get_active_provider_name,
    )

    # Test explicit groq routing
    with patch.dict("os.environ", {"GROQ_API_KEY": "gsk_test_valid"}):
        with patch("app.config.settings.GROQ_API_KEY", "gsk_test_valid"):
            set_active_provider_name("groq")
            assert get_active_provider_name() == "groq"
            prov = get_provider("groq")
            assert prov.provider_name == "groq"
            assert prov.is_local is False

    # Test fallback to ollama when groq key missing
    with patch.dict("os.environ", {"GROQ_API_KEY": ""}, clear=True):
        with patch("app.config.settings.GROQ_API_KEY", ""):
            with patch("app.config.settings.FALLBACK_TO_LOCAL", True):
                fallback = get_provider("groq", fallback_on_error=True)
                assert fallback.provider_name == "ollama"
                assert fallback.is_local is True
