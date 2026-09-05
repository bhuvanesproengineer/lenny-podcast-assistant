from abc import ABC, abstractmethod
from typing import Optional, AsyncGenerator, Any

class BaseProvider(ABC):
    """
    Abstract base provider interface for the Dual Model Layer.
    Defines common inference and skill generation methods for both
    Local (Ollama) and Cloud (Claude / OpenRouter) models.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Returns the human-readable identifier of the provider (e.g., 'ollama', 'cloud')."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Returns the specific model identifier (e.g., 'llama3.2:3b', 'anthropic/claude-sonnet-4')."""
        pass

    @property
    def is_local(self) -> bool:
        """Whether this provider runs locally on device without external network calls."""
        return False

    @abstractmethod
    async def generate_response(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> str:
        """
        Common interface method: Generates a complete response for general queries or Q&A.
        """
        pass

    @abstractmethod
    async def generate_ship30_article(
        self,
        topic: str,
        context: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.4,
        **kwargs: Any,
    ) -> str:
        """
        Common interface method: Generates a complete Ship30 growth article with standard sections.
        """
        pass

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> str:
        """
        Backward-compatible generation method.
        """
        pass

    @abstractmethod
    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """
        Yields tokens/chunks as an asynchronous generator.
        """
        pass


# Backward-compatibility alias
BaseLLMProvider = BaseProvider
