import asyncio
import logging
import os
import time
from typing import List, Optional, Dict, Any, Union

from app.config import settings
from app.rag.embeddings import EmbeddingGenerator

logger = logging.getLogger("embedding_router")

# Runtime override for dynamic UI switching if needed
_runtime_embedding_provider_override: Optional[str] = None


def get_active_embedding_provider() -> str:
    """
    Returns the currently active embedding provider ('ollama' or 'gemini').

    Strict Provider Isolation Routing:
    1. Runtime override (_runtime_embedding_provider_override) takes highest precedence.
    2. Active LLM Provider routing:
       - If active LLM is 'cloud' or 'groq':
           -> Enforces 'gemini' embeddings (queries transcript_chunks_gemini).
              Never calls localhost:11434.
       - If active LLM is 'ollama':
           -> Enforces 'ollama' embeddings (queries transcript_chunks).
              Unless environment explicitly sets EMBEDDING_PROVIDER=gemini.
    3. Fallback to EMBEDDING_PROVIDER environment variable, or 'ollama'.
    """
    global _runtime_embedding_provider_override
    if _runtime_embedding_provider_override:
        return _runtime_embedding_provider_override.lower().strip()

    from app.providers.provider_factory import get_active_provider_name
    active_llm = get_active_provider_name()

    if active_llm in ("cloud", "groq"):
        return "gemini"
    elif active_llm == "ollama":
        env_emb = os.getenv("EMBEDDING_PROVIDER", "").lower().strip()
        if env_emb == "gemini":
            return "gemini"
        return "ollama"

    env_emb = os.getenv("EMBEDDING_PROVIDER", getattr(settings, "EMBEDDING_PROVIDER", "ollama")).lower().strip()
    if env_emb == "gemini":
        return "gemini"
    return "ollama"


def set_active_embedding_provider(name: str) -> str:
    """
    Sets runtime active embedding provider ('ollama' or 'gemini').
    """
    global _runtime_embedding_provider_override
    clean = name.lower().strip()
    if clean not in ("ollama", "gemini"):
        raise ValueError(f"Invalid embedding provider '{name}'. Must be 'ollama' or 'gemini'.")
    _runtime_embedding_provider_override = clean
    logger.info("Active embedding provider switched to: %s", clean)
    return clean


def reset_active_embedding_provider() -> None:
    """Resets runtime active embedding provider override to default environment settings."""
    global _runtime_embedding_provider_override
    _runtime_embedding_provider_override = None


class GeminiEmbeddingGenerator:
    """
    Cloud embedding generator using Google GenAI SDK (768 dimensions).
    Completely isolated from local Ollama:
    - Never calls localhost:11434
    - Never invokes nomic-embed-text
    - Uses Google API key and models (gemini-embedding-001, gemini-embedding-2, etc.)
    """

    FALLBACK_POOL = ["gemini-embedding-001", "gemini-embedding-2", "gemini-embedding-2-preview"]

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 60.0
    ):
        self.api_key = (
            api_key
            or os.getenv("GOOGLE_API_KEY")
            or getattr(settings, "GOOGLE_API_KEY", "")
            or ""
        )
        # Read EMBEDDING_MODEL from environment / .env, falling back to gemini-embedding-001
        env_model = os.getenv("EMBEDDING_MODEL") or os.getenv("GEMINI_EMBEDDING_MODEL")
        if env_model and "nomic" not in env_model.lower() and "text-embedding-004" not in env_model.lower():
            selected_model = env_model
        else:
            selected_model = getattr(settings, "GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")

        self.model = model or selected_model
        self.timeout = timeout
        self._client = None
        self._current_idx = 0
        self.model_cooldowns: Dict[str, float] = {}

    @property
    def provider(self) -> str:
        return "gemini"

    @property
    def dimension(self) -> int:
        return 768

    def _get_client(self):
        if self._client is None:
            if not self.api_key:
                raise RuntimeError("Gemini embedding requested but no GOOGLE_API_KEY is configured.")
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def _get_candidate_models(self) -> List[str]:
        models = [self.model]
        for m in self.FALLBACK_POOL:
            if m not in models:
                models.append(m)
        return models

    def _get_available_model(self) -> str:
        candidates = self._get_candidate_models()
        now = time.time()
        for i in range(len(candidates)):
            idx = (self._current_idx + i) % len(candidates)
            cand = candidates[idx]
            if now >= self.model_cooldowns.get(cand, 0.0):
                self._current_idx = idx
                return cand
        # If all in cooldown, pick primary and attempt anyway
        return candidates[0]

    async def verify_embedding_model_exists(self) -> Dict[str, Any]:
        """
        Verifies that the configured Gemini embedding model exists in Google GenAI API
        and tests generating a test embedding for 'hello world' before enabling retrieval.
        """
        client = self._get_client()
        loop = asyncio.get_running_loop()

        # 1. Verify model metadata exists
        def _get_model():
            return client.models.get(model=self.model)

        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:embedContent"
        try:
            model_info = await loop.run_in_executor(None, _get_model)
            model_name = getattr(model_info, "name", self.model)
            logger.info("Verified Gemini embedding model exists: %s", model_name)
        except Exception as exc:
            resp_body = getattr(exc, "response_json", None) or getattr(exc, "message", str(exc))
            logger.error(
                "Gemini model existence check failed:\n"
                "  Model Name: %s\n"
                "  Endpoint: %s\n"
                "  Response Body: %s",
                self.model,
                endpoint,
                resp_body,
            )
            print(
                f"[ERROR] Gemini Model Verification Failed:\n"
                f"  Exact Model Name: {self.model}\n"
                f"  Endpoint: {endpoint}\n"
                f"  Response Body: {resp_body}",
                flush=True
            )
            return {"exists": False, "model": self.model, "error": str(resp_body)}

        # 2. Test generating an embedding for 'hello world'
        test_text = "hello world"
        try:
            from google.genai import types
            def _test_embed():
                config = types.EmbedContentConfig(output_dimensionality=768)
                return client.models.embed_content(
                    model=self.model,
                    contents=test_text,
                    config=config,
                )

            res = await loop.run_in_executor(None, _test_embed)
            dim = len(res.embeddings[0].values) if res and res.embeddings else 0
            logger.info("Test embedding for '%s' generated successfully (dim=%d)", test_text, dim)
            print(f"[INFO] Gemini Test Embedding for '{test_text}' SUCCESS (dim={dim})", flush=True)
            return {"exists": True, "tested": True, "dimension": dim, "model": self.model}
        except Exception as exc:
            resp_body = getattr(exc, "response_json", None) or getattr(exc, "message", str(exc))
            logger.warning(
                "Gemini test embedding for '%s' returned: %s. Endpoint: %s",
                test_text, resp_body, endpoint
            )
            return {"exists": True, "tested": False, "error": str(resp_body), "model": self.model}

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generates 768-dim embeddings for a list of texts asynchronously."""
        if not texts:
            return []

        client = self._get_client()
        from google.genai import types

        model = self._get_available_model()
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent"

        def _call_api():
            config = types.EmbedContentConfig(output_dimensionality=768)
            return client.models.embed_content(
                model=model,
                contents=texts,
                config=config,
            )

        loop = asyncio.get_running_loop()
        try:
            resp = await loop.run_in_executor(None, _call_api)
            embeddings = [list(e.values) for e in resp.embeddings]
            if embeddings and len(embeddings[0]) != 768:
                logger.warning("Gemini returned unexpected dimension: %d", len(embeddings[0]))
            return embeddings
        except Exception as exc:
            response_body = (
                getattr(exc, "response_json", None)
                or getattr(exc, "message", None)
                or str(exc)
            )
            logger.error(
                "Gemini embedding failed:\n"
                "  Exact Model Name: %s\n"
                "  Endpoint: %s\n"
                "  Response Body: %s",
                model,
                endpoint,
                response_body,
                exc_info=True
            )
            print(
                f"[ERROR] Gemini Embedding Failed:\n"
                f"  Exact Model Name: {model}\n"
                f"  Endpoint: {endpoint}\n"
                f"  Response Body: {response_body}",
                flush=True
            )

            exc_str = str(exc)
            if "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str:
                self.model_cooldowns[model] = time.time() + 60.0
                self._current_idx = (self._current_idx + 1) % len(self.FALLBACK_POOL)
                next_model = self._get_available_model()
                if next_model != model:
                    fallback_endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{next_model}:embedContent"
                    def _call_fallback():
                        config = types.EmbedContentConfig(output_dimensionality=768)
                        return client.models.embed_content(
                            model=next_model,
                            contents=texts,
                            config=config,
                        )
                    try:
                        resp = await loop.run_in_executor(None, _call_fallback)
                        return [list(e.values) for e in resp.embeddings]
                    except Exception as fb_exc:
                        fb_body = getattr(fb_exc, "response_json", None) or str(fb_exc)
                        logger.error(
                            "Gemini fallback embedding failed:\n"
                            "  Exact Model Name: %s\n"
                            "  Endpoint: %s\n"
                            "  Response Body: %s",
                            next_model,
                            fallback_endpoint,
                            fb_body,
                        )
            raise RuntimeError(
                f"Gemini embedding failed for model '{model}' at endpoint '{endpoint}': {response_body}"
            ) from exc

    async def get_single_embedding(self, text: str) -> List[float]:
        """Generates a 768-dim embedding for a single text."""
        res = await self.get_embeddings([text])
        if not res:
            raise ValueError("No embedding returned from Gemini")
        return res[0]


def get_embedding_generator(provider: Optional[str] = None) -> Union[EmbeddingGenerator, GeminiEmbeddingGenerator]:
    """
    Router returning the embedding generator for the requested or active provider:
    - 'ollama': returns EmbeddingGenerator (Ollama, nomic-embed-text)
    - 'gemini': returns GeminiEmbeddingGenerator (Google GenAI, 768 dim)
    """
    target = (provider or get_active_embedding_provider()).lower().strip()
    if target == "gemini":
        return GeminiEmbeddingGenerator()
    return EmbeddingGenerator()


def get_embedding_info() -> Dict[str, Any]:
    """Returns diagnostics for active embedding setup."""
    active = get_active_embedding_provider()
    if active == "gemini":
        env_model = os.getenv("EMBEDDING_MODEL", "")
        if env_model and "gemini" in env_model.lower():
            model = env_model
        else:
            model = getattr(settings, "GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
        return {
            "provider": "gemini",
            "model": model,
            "table": "transcript_chunks_gemini",
            "dimension": 768,
        }

    env_model = os.getenv("EMBEDDING_MODEL", "")
    if env_model and "gemini" not in env_model.lower():
        model = env_model
    else:
        model = getattr(settings, "EMBEDDING_MODEL", "nomic-embed-text")
    if "gemini" in model.lower():
        model = "nomic-embed-text"

    return {
        "provider": "ollama",
        "model": model,
        "table": "transcript_chunks",
        "dimension": getattr(settings, "EMBEDDING_DIMENSION", 768),
    }
