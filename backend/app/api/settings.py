import logging
from fastapi import APIRouter, HTTPException, status

from app.providers.provider_factory import (
    get_active_provider_name,
    set_active_provider_name,
    get_provider_status,
)
from app.models.schemas import SetProviderRequest, ProviderSettingsResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/provider", response_model=ProviderSettingsResponse)
async def get_current_provider_settings():
    """
    Returns the current Dual Model Layer configuration, active provider,
    and availability status for Local (Ollama) and Cloud (Claude).
    """
    try:
        status_info = get_provider_status()
        return ProviderSettingsResponse.model_validate(status_info)
    except Exception as exc:
        logger.error("Failed to retrieve provider settings: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve provider configuration",
        ) from exc


@router.post("/provider", response_model=ProviderSettingsResponse)
async def set_active_provider(payload: SetProviderRequest):
    """
    Switches the active LLM provider between 'ollama' and 'cloud' dynamically.
    No backend code restart or server downtime required.
    """
    try:
        new_provider = set_active_provider_name(payload.provider)
        logger.info("Switched active provider to '%s'", new_provider)
        status_info = get_provider_status()
        return ProviderSettingsResponse.model_validate(status_info)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("Failed to switch provider: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to switch active provider",
        ) from exc
