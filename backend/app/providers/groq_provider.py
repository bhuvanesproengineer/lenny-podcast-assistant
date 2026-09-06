import asyncio
import json
import logging
import os
from typing import Optional, AsyncGenerator, Any, Dict
import httpx

from app.config import settings
from app.providers.base_provider import BaseProvider

logger = logging.getLogger("groq_provider")


class GroqProvider(BaseProvider):
    """
    Cloud LLM provider using Groq OpenAI-compatible API.
    Provides high-speed inference for Chat, RAG generation, and Ship30 articles.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 120.0,
    ):
        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = (
                os.getenv("GROQ_API_KEY")
                if "GROQ_API_KEY" in os.environ
                else getattr(settings, "GROQ_API_KEY", "")
            ) or ""
        self.base_url = (
            base_url
            or os.getenv("GROQ_BASE_URL")
            or getattr(settings, "GROQ_BASE_URL", "https://api.groq.com/openai/v1")
        ).rstrip("/")
        self.model = (
            model
            or os.getenv("GROQ_MODEL")
            or os.getenv("MODEL")
            or getattr(settings, "GROQ_MODEL", "openai/gpt-oss-20b")
        )
        self.timeout = timeout

    @property
    def provider_name(self) -> str:
        return "groq"

    @property
    def model_name(self) -> str:
        return self.model

    @property
    def is_local(self) -> bool:
        return False

    def is_configured(self) -> bool:
        """Returns True if a Groq API key is present."""
        return bool(self.api_key and self.api_key.strip())

    async def generate_response(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> str:
        """
        Common interface method: Generates a complete response for Q&A or RAG synthesis.
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
        Common interface method: Generates a complete Ship30 article using Groq.
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
            max_tokens=kwargs.get("max_tokens", kwargs.get("num_predict", 3000)),
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
        Generates a non-streaming completion response via Groq API.
        """
        if not self.is_configured():
            raise RuntimeError(
                "GroqProvider requires an API key (GROQ_API_KEY). "
                "Please configure GROQ_API_KEY in .env or switch to Ollama."
            )

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
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

        # TPM Protection & Token Estimation for Cloud Mode
        from app.rag.cloud_optimizations import get_cloud_tpm_tracker, estimate_tokens
        prompt_text = (system_prompt or "") + " " + prompt
        estimated_tokens = estimate_tokens(prompt_text) + int(payload.get("max_tokens", 500))
        tracker = get_cloud_tpm_tracker()
        await tracker.acquire(estimated_tokens)

        max_retries = kwargs.get("max_retries", 3)
        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(url, json=payload, headers=headers)
                    if response.status_code == 429 and attempt < max_retries:
                        retry_after = float(response.headers.get("retry-after", 2.0))
                        logger.warning(
                            "Groq rate limit (429) on attempt %d/%d. Waiting %.2fs...",
                            attempt, max_retries, retry_after
                        )
                        await asyncio.sleep(retry_after)
                        continue
                    response.raise_for_status()
                    data = response.json()
                    choices = data.get("choices", [])
                    if choices:
                        msg = choices[0].get("message", {})
                        content = msg.get("content")
                        if content is not None and content.strip():
                            return content.strip()
                        # Fallback if content was placed in reasoning or other field
                        reasoning = msg.get("reasoning", "")
                        if reasoning:
                            return reasoning.strip()
                    return ""
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429 and attempt < max_retries:
                    retry_after = float(exc.response.headers.get("retry-after", 2.0))
                    logger.warning(
                        "Groq rate limit (429) on attempt %d/%d. Waiting %.2fs...",
                        attempt, max_retries, retry_after
                    )
                    await asyncio.sleep(retry_after)
                    continue
                logger.error(
                    f"Groq generation failed for model '{self.model}' at '{url}': {exc}",
                    exc_info=True,
                )
                raise RuntimeError(f"Groq generation error: {exc}") from exc
            except Exception as exc:
                if attempt < max_retries:
                    await asyncio.sleep(1.0)
                    continue
                logger.error(
                    f"Groq generation failed for model '{self.model}' at '{url}': {exc}",
                    exc_info=True,
                )
                raise RuntimeError(f"Groq generation error: {exc}") from exc

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
                "GroqProvider requires an API key (GROQ_API_KEY)."
            )

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
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
        elif "num_predict" in kwargs:
            payload["max_tokens"] = kwargs["num_predict"]

        # TPM Protection & Token Estimation for Cloud Mode
        from app.rag.cloud_optimizations import get_cloud_tpm_tracker, estimate_tokens
        prompt_text = (system_prompt or "") + " " + prompt
        estimated_tokens = estimate_tokens(prompt_text) + int(payload.get("max_tokens", 500))
        tracker = get_cloud_tpm_tracker()
        await tracker.acquire(estimated_tokens)

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
                f"Groq streaming failed for model '{self.model}': {exc}",
                exc_info=True,
            )
            raise RuntimeError(f"Groq streaming error: {exc}") from exc
