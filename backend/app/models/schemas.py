from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict


class CreateSessionRequest(BaseModel):
    """Optional payload when creating a new session."""
    title: Optional[str] = Field(default=None, description="Optional custom session title")

    @field_validator("title")
    @classmethod
    def clean_title(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            return v if v else None
        return None


class CreateSessionResponse(BaseModel):
    """Response returned after creating a new session."""
    session_id: str
    title: str


class UpdateSessionRequest(BaseModel):
    """Payload for renaming a session."""
    title: str = Field(..., min_length=1, max_length=255, description="New session title")

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("title cannot be empty or whitespace.")
        return clean


class MessageResponse(BaseModel):
    """Schema representing an individual message in a chat history."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: str
    role: str
    content: str
    created_at: datetime


class SessionSummaryResponse(BaseModel):
    """Schema representing a summary of a chat session."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: Optional[str]
    created_at: datetime
    updated_at: datetime


class SessionDetailResponse(BaseModel):
    """Schema representing full session details including message history."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: Optional[str]
    created_at: datetime
    updated_at: datetime
    messages: List[MessageResponse] = []



class ChatRequest(BaseModel):
    """Payload for submitting a user message to the chat endpoint."""
    session_id: str = Field(..., description="Unique ID of the existing chat session")
    message: str = Field(..., min_length=1, description="User question or message text")

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("session_id cannot be empty or whitespace.")
        return clean

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("message cannot be empty or whitespace.")
        return clean


class ChatResponse(BaseModel):
    """Response returned from the chat orchestration endpoint."""
    session_id: str
    answer: str
    sources: List[str] = []
    selected_tool: Optional[str] = None
    artifact: bool = False
    markdown_content: Optional[str] = None
    html_content: Optional[str] = None
    word_count: Optional[int] = None


class SetProviderRequest(BaseModel):
    """Payload for changing the active LLM provider."""
    provider: str = Field(..., description="Target provider ('ollama', 'groq', or 'cloud')")

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in ("ollama", "cloud", "groq"):
            raise ValueError("Provider must be 'ollama', 'groq', or 'cloud'.")
        return clean


class ProviderInfo(BaseModel):
    name: str
    model: str
    base_url: str
    available: bool


class ProviderSettingsResponse(BaseModel):
    """Response schema representing current Dual Model Layer configuration."""
    active_provider: str
    local: ProviderInfo
    cloud: ProviderInfo
    fallback_enabled: bool
