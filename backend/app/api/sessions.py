import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.session_service import (
    SessionService,
    SessionNotFoundError,
    SessionServiceError
)
from app.models.schemas import (
    CreateSessionRequest,
    CreateSessionResponse,
    UpdateSessionRequest,
    SessionSummaryResponse,
    SessionDetailResponse,
    MessageResponse
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sessions"])


@router.post("/session/new", response_model=CreateSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_new_session(
    payload: Optional[CreateSessionRequest] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Creates a new chat session.
    Accepts an optional title, defaulting to 'New Chat' if not provided.
    Returns the generated session_id and title.
    """
    title = payload.title if payload else None
    logger.info("Handling POST /session/new", extra={"title": title})

    try:
        session = await SessionService.create_session(db, title=title)
        return CreateSessionResponse(
            session_id=session.id,
            title=session.title
        )
    except SessionServiceError as exc:
        logger.error("Failed to create session: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create session"
        ) from exc


@router.get("/sessions", response_model=List[SessionSummaryResponse])
async def list_all_sessions(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
):
    """
    Lists all chat sessions ordered by updated_at descending.
    Supports optional pagination via skip and limit query parameters.
    """
    logger.debug("Handling GET /sessions", extra={"skip": skip, "limit": limit})
    try:
        sessions = await SessionService.list_sessions(db, skip=skip, limit=limit)
        return [
            SessionSummaryResponse.model_validate(s)
            for s in sessions
        ]
    except SessionServiceError as exc:
        logger.error("Failed to list sessions: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve sessions"
        ) from exc


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session_details(
    session_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieves a session's details and its complete chronological conversation history.
    Returns 404 if the session ID is not found.
    """
    clean_id = session_id.strip()
    logger.debug("Handling GET /sessions/%s", clean_id)

    session = await SessionService.get_session(db, clean_id)
    if session is None:
        logger.warning("Session not found: %s", clean_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{clean_id}' not found"
        )

    try:
        messages = await SessionService.get_session_messages(db, clean_id)
        return SessionDetailResponse(
            id=session.id,
            title=session.title,
            created_at=session.created_at,
            updated_at=session.updated_at,
            messages=[MessageResponse.model_validate(m) for m in messages]
        )
    except SessionServiceError as exc:
        logger.error("Failed to retrieve messages for session %s: %s", clean_id, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve session messages"
        ) from exc


@router.patch("/sessions/{session_id}", response_model=SessionSummaryResponse)
async def update_session(
    session_id: str,
    payload: UpdateSessionRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Renames an existing chat session.
    """
    clean_id = session_id.strip()
    logger.info("Handling PATCH /sessions/%s", clean_id, extra={"title": payload.title})
    try:
        session = await SessionService.update_session_title(db, clean_id, payload.title)
        return SessionSummaryResponse.model_validate(session)
    except SessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{clean_id}' not found"
        ) from exc
    except SessionServiceError as exc:
        logger.error("Failed to rename session %s: %s", clean_id, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to rename session"
        ) from exc


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session_endpoint(
    session_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Deletes a chat session and all its conversation messages.
    """
    clean_id = session_id.strip()
    logger.info("Handling DELETE /sessions/%s", clean_id)
    try:
        await SessionService.delete_session(db, clean_id)
        return None
    except SessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{clean_id}' not found"
        ) from exc
    except SessionServiceError as exc:
        logger.error("Failed to delete session %s: %s", clean_id, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete session"
        ) from exc
