import json
import logging
from typing import Optional, AsyncGenerator, Any, Dict
import httpx

from app.config import settings
from app.providers.base_provider import BaseProvider

logger = logging.getLogger("ollama_provider")


class OllamaProvider(BaseProvider):
    """
    Local LLM provider using Ollama instance (Mandatory Local Demo: llama3.2:3b).
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 120.0
    ):
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or getattr(settings, "OLLAMA_DEFAULT_MODEL", "llama3.2:3b")
        self.timeout = timeout

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self.model

    @property
    def is_local(self) -> bool:
        return True

    async def generate_response(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> str:
        """
        Common interface method: Generates a complete response for Q&A or agent intent.
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
        Common interface method: Generates a complete Ship30 article using Ollama.
        """
        prompt = (
            f"Write a comprehensive Ship 30 for 30 style growth article on the topic:\n"
            f"\"{topic}\"\n\n"
        )
        if context:
            prompt += f"Use the following podcast transcript context:\n{context}\n\n"
        prompt += (
            "Ensure the article follows the standard Ship30 format:\n"
            "# [Actionable Title]\n"
            "## Hook\n"
            "## Problem\n"
            "## Insight\n"
            "## Lesson\n"
            "## Application\n"
            "## Action Steps\n"
        )
        return await self.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            num_predict=kwargs.get("num_predict", 3000),
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
        Generates a complete response from the Ollama model.
        """
        url = f"{self.base_url}/api/generate"
        options = {
            "temperature": temperature,
            "num_predict": kwargs.get("num_predict", 2048),
        }
        if "options" in kwargs and isinstance(kwargs["options"], dict):
            options.update(kwargs["options"])

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": options,
        }
        if system_prompt:
            payload["system"] = system_prompt

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                return data.get("response", "").strip()
        except Exception as exc:
            logger.error(f"Ollama generation failed for model '{self.model}': {exc}", exc_info=True)
            raise RuntimeError(f"Ollama generation error: {exc}") from exc

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """
        Streams generated tokens incrementally.
        """
        url = f"{self.base_url}/api/generate"
        options = {
            "temperature": temperature,
            "num_predict": kwargs.get("num_predict", 2048),
        }
        if "options" in kwargs and isinstance(kwargs["options"], dict):
            options.update(kwargs["options"])

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "options": options,
        }
        if system_prompt:
            payload["system"] = system_prompt

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", url, json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        chunk_data = json.loads(line)
                        yield chunk_data.get("response", "")
        except Exception as exc:
            logger.error(f"Ollama streaming failed for model '{self.model}': {exc}", exc_info=True)
            raise RuntimeError(f"Ollama streaming error: {exc}") from exc
