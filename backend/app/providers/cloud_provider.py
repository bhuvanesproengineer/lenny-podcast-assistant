import json
import logging
import os
from typing import Optional, AsyncGenerator, Any, Dict
import httpx

from app.config import settings
from app.providers.base_provider import BaseProvider

logger = logging.getLogger("cloud_provider")


class CloudProvider(BaseProvider):
    """
    Cloud LLM provider using OpenRouter (preferred: anthropic/claude-sonnet-4)
    or OpenAI-compatible chat completion APIs.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 120.0,
    ):
        # OpenRouter API Key preferred, with fallback to Anthropic / OpenAI keys
        self.api_key = (
            api_key
            or os.getenv("OPENROUTER_API_KEY")
            or settings.OPENROUTER_API_KEY
            or os.getenv("ANTHROPIC_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or ""
        )
        
        # Base URL: default to OpenRouter if using OpenRouter key, else OpenAI / custom
        default_base_url = (
            settings.OPENROUTER_BASE_URL
            if (os.getenv("OPENROUTER_API_KEY") or settings.OPENROUTER_API_KEY or not os.getenv("OPENAI_API_KEY"))
            else "https://api.openai.com/v1"
        )
        self.base_url = (base_url or os.getenv("OPENROUTER_BASE_URL") or default_base_url).rstrip("/")
        
        # Default model: anthropic/claude-sonnet-4
        self.model = (
            model
            or os.getenv("CLOUD_MODEL")
            or settings.CLOUD_MODEL
            or "anthropic/claude-sonnet-4"
        )
        self.timeout = timeout

    @property
    def provider_name(self) -> str:
        return "cloud"

    @property
    def model_name(self) -> str:
        return self.model

    @property
    def is_local(self) -> bool:
        return False

    def is_configured(self) -> bool:
        """Returns True if a cloud API key is present."""
        return bool(self.api_key and self.api_key.strip())

    async def generate_response(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> str:
        """
        Common interface method: Generates a complete response using Claude Cloud.
        """
        return await self.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            **kwargs,
        )

    async def generate_ship30_article(
        self,
        topic: str,
        context: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.4,
        **kwargs: Any,
    ) -> str:
        """
        Common interface method: Generates a full Ship30 article using Claude Cloud.
        """
        prompt = (
            f"Write an authoritative, high-impact Ship 30 for 30 style growth article on the topic:\n"
            f"\"{topic}\"\n\n"
        )
        if context:
            prompt += f"Ground your writing in the following Lenny's Podcast transcript excerpts:\n{context}\n\n"
        prompt += (
            "Ensure the article strictly adheres to the standard Ship30 structure:\n"
            "# [Action-Oriented Title]\n"
            "## Hook\n"
            "## Problem\n"
            "## Insight\n"
            "## Lesson\n"
            "## Application\n"
            "## Action Steps\n"
            "## Sources\n"
        )
        return await self.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=kwargs.get("max_tokens", 4000),
            **kwargs,
        )

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> str:
        """
        Generates a non-streaming completion response via OpenRouter / OpenAI-compatible chat API.
        """
        if not self.is_configured():
            raise RuntimeError(
                "CloudProvider requires an API key (OPENROUTER_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY). "
                "Please configure OPENROUTER_API_KEY in .env or switch to Ollama."
            )

        referer = getattr(settings, "CORS_ORIGINS", "http://localhost:3000").split(",")[0].strip()
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": referer,
            "X-Title": "Lenny Growth Assistant",
        }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if "max_tokens" in kwargs:
            payload["max_tokens"] = kwargs["max_tokens"]
        elif "num_predict" in kwargs:
            payload["max_tokens"] = kwargs["num_predict"]
        else:
            payload["max_tokens"] = 3000

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                choices = data.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "").strip()
                return ""
        except Exception as exc:
            logger.error(
                f"Cloud generation failed for model '{self.model}' at '{url}': {exc}",
                exc_info=True,
            )
            raise RuntimeError(f"Cloud generation error: {exc}") from exc

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """
        Streams generated tokens incrementally via Server-Sent Events (SSE).
        """
        if not self.is_configured():
            raise RuntimeError(
                "CloudProvider requires an API key (OPENROUTER_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY)."
            )

        referer = getattr(settings, "CORS_ORIGINS", "http://localhost:3000").split(",")[0].strip()
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": referer,
            "X-Title": "Lenny Growth Assistant",
        }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if "max_tokens" in kwargs:
            payload["max_tokens"] = kwargs["max_tokens"]

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line or not line.startswith("data: "):
                            continue
                        data_str = line[len("data: "):].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk_data = json.loads(data_str)
                            choices = chunk_data.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield content
                        except json.JSONDecodeError:
                            continue
        except Exception as exc:
            logger.error(
                f"Cloud streaming failed for model '{self.model}': {exc}",
                exc_info=True,
            )
            raise RuntimeError(f"Cloud streaming error: {exc}") from exc
