import logging
import os
from typing import Optional, Dict, Any

from app.config import settings
from app.providers.base_provider import BaseProvider
from app.providers.ollama_provider import OllamaProvider
from app.providers.cloud_provider import CloudProvider

logger = logging.getLogger("provider_factory")

# Global runtime override (allows setting provider dynamically via API/UI)
_runtime_provider_override: Optional[str] = None


def get_active_provider_name() -> str:
    """
    Returns the currently active provider name ('ollama' or 'cloud').
    Prioritizes runtime UI selection, falling back to LLM_PROVIDER in settings / .env.
    """
    global _runtime_provider_override
    if _runtime_provider_override:
        return _runtime_provider_override.lower().strip()
    return getattr(settings, "LLM_PROVIDER", "ollama").lower().strip()


def set_active_provider_name(name: str) -> str:
    """
    Sets the runtime active provider ('ollama' or 'cloud').
    """
    global _runtime_provider_override
    clean = name.lower().strip()
    if clean not in ("ollama", "cloud"):
        raise ValueError(f"Invalid provider '{name}'. Must be 'ollama' or 'cloud'.")
    _runtime_provider_override = clean
    logger.info("Active LLM provider switched to: %s", clean)
    return clean


def get_provider(
    provider_type: Optional[str] = None,
    fallback_on_error: bool = True
) -> BaseProvider:
    """
    Factory function returning the configured BaseProvider instance.
    
    If provider == "ollama":
        returns OllamaProvider()
    if provider == "cloud":
        returns CloudProvider()
        
    If cloud is requested but unconfigured or fails, automatically falls back
    to OllamaProvider when fallback_on_error is True.
    """
    requested = (provider_type or get_active_provider_name()).lower().strip()
    logger.debug("ProviderFactory resolving provider: requested='%s'", requested)

    if requested == "cloud":
        try:
            cloud_provider = CloudProvider()
            if not cloud_provider.is_configured():
                if fallback_on_error and getattr(settings, "FALLBACK_TO_LOCAL", True):
                    logger.warning(
                        "Cloud provider requested but no API key configured. "
                        "Falling back gracefully to local Ollama (%s).",
                        settings.OLLAMA_DEFAULT_MODEL
                    )
                    return OllamaProvider()
                else:
                    raise RuntimeError("Cloud provider requested but no API key configured.")
            return cloud_provider
        except Exception as exc:
            if fallback_on_error and getattr(settings, "FALLBACK_TO_LOCAL", True):
                logger.error(
                    "Failed to initialize CloudProvider: %s. Falling back to local Ollama.",
                    exc,
                    exc_info=True
                )
                return OllamaProvider()
            raise

    # Default: local Ollama
    return OllamaProvider()


def get_provider_status() -> Dict[str, Any]:
    """
    Returns full diagnostics and current status of the Dual Model Layer.
    """
    active = get_active_provider_name()
    cloud_inst = CloudProvider()
    is_cloud_available = cloud_inst.is_configured()

    return {
        "active_provider": active,
        "local": {
            "name": "ollama",
            "model": getattr(settings, "OLLAMA_DEFAULT_MODEL", "llama3.2:3b"),
            "base_url": getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434"),
            "available": True,
        },
        "cloud": {
            "name": "cloud",
            "model": getattr(settings, "CLOUD_MODEL", "anthropic/claude-sonnet-4"),
            "base_url": getattr(settings, "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            "available": is_cloud_available,
        },
        "fallback_enabled": getattr(settings, "FALLBACK_TO_LOCAL", True),
    }
