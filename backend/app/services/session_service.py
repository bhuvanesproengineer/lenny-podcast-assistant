import logging
from typing import List, Optional
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from app.models.db_models import Session, Message

logger = logging.getLogger(__name__)

# Valid roles for conversation messages
ALLOWED_ROLES = {"user", "assistant"}


class SessionServiceError(Exception):
    """Base exception for session service operations."""
    pass


class SessionNotFoundError(SessionServiceError):
    """Raised when a requested session is not found."""
    pass


class InvalidRoleError(SessionServiceError, ValueError):
    """Raised when an invalid role is provided for a message."""
    pass


class EmptyMessageError(SessionServiceError, ValueError):
    """Raised when message content is empty or whitespace-only."""
    pass


class SessionService:
    """
    Service layer providing CRUD operations and business logic for chat sessions
    and message persistence.
    """

    @staticmethod
    async def create_session(
        db: AsyncSession,
        title: Optional[str] = None
    ) -> Session:
        """
        Creates a new chat session with an optional title.
        Defaults title to 'New Chat' if not provided or empty.
        """
        cleaned_title = title.strip() if title and title.strip() else "New Chat"
        logger.info("Creating chat session", extra={"title": cleaned_title})

        try:
            session = Session(title=cleaned_title)
            db.add(session)
            await db.commit()
            await db.refresh(session)
            logger.info("Chat session created", extra={"session_id": session.id, "title": session.title})
            return session
        except SQLAlchemyError as exc:
            await db.rollback()
            logger.error("Failed to create chat session: %s", exc, exc_info=True)
            raise SessionServiceError(f"Database error while creating session: {exc}") from exc

    @staticmethod
    async def get_session(
        db: AsyncSession,
        session_id: str
    ) -> Optional[Session]:
        """
        Retrieves a session by its unique ID. Returns None if not found.
        """
        if not session_id or not isinstance(session_id, str) or not session_id.strip():
            return None

        clean_id = session_id.strip()
        logger.debug("Fetching chat session", extra={"session_id": clean_id})

        try:
            stmt = select(Session).where(Session.id == clean_id)
            result = await db.execute(stmt)
            session = result.scalars().first()
            if session:
                logger.debug("Found chat session", extra={"session_id": clean_id})
            else:
                logger.debug("Chat session not found", extra={"session_id": clean_id})
            return session
        except SQLAlchemyError as exc:
            logger.error("Failed to retrieve chat session '%s': %s", clean_id, exc, exc_info=True)
            raise SessionServiceError(f"Database error while fetching session: {exc}") from exc

    @staticmethod
    async def list_sessions(
        db: AsyncSession,
        skip: int = 0,
        limit: int = 50
    ) -> List[Session]:
        """
        Lists all chat sessions ordered by most recently updated first.
        Supports pagination with skip and limit parameters.
        """
        safe_skip = max(0, skip)
        safe_limit = max(1, min(100, limit))

        logger.debug("Listing chat sessions", extra={"skip": safe_skip, "limit": safe_limit})

        try:
            stmt = (
                select(Session)
                .order_by(Session.updated_at.desc(), Session.created_at.desc())
                .offset(safe_skip)
                .limit(safe_limit)
            )
            result = await db.execute(stmt)
            sessions = list(result.scalars().all())
            logger.debug("Listed %d chat sessions", len(sessions))
            return sessions
        except SQLAlchemyError as exc:
            logger.error("Failed to list chat sessions: %s", exc, exc_info=True)
            raise SessionServiceError(f"Database error while listing sessions: {exc}") from exc

    @staticmethod
    async def add_message(
        db: AsyncSession,
        session_id: str,
        role: str,
        content: str
    ) -> Message:
        """
        Appends a message to the specified session.
        Validates the role ('user' or 'assistant') and ensures content is non-empty.
        Updates the session's updated_at timestamp.
        """
        if not session_id or not isinstance(session_id, str) or not session_id.strip():
            raise SessionNotFoundError("A valid session_id must be provided.")

        clean_session_id = session_id.strip()

        # Validate role
        if not role or not isinstance(role, str):
            raise InvalidRoleError("Message role must be a non-empty string.")

        normalized_role = role.strip().lower()
        if normalized_role not in ALLOWED_ROLES:
            raise InvalidRoleError(
                f"Invalid role '{role}'. Allowed roles are: {', '.join(sorted(ALLOWED_ROLES))}."
            )

        # Validate content
        if not content or not isinstance(content, str) or not content.strip():
            raise EmptyMessageError("Message content cannot be empty or whitespace-only.")

        cleaned_content = content.strip()

        # Verify session existence
        session = await SessionService.get_session(db, clean_session_id)
        if session is None:
            logger.warning("Attempted to add message to non-existent session", extra={"session_id": clean_session_id})
            raise SessionNotFoundError(f"Session '{clean_session_id}' does not exist.")

        logger.info(
            "Adding message to session",
            extra={"session_id": clean_session_id, "role": normalized_role, "length": len(cleaned_content)}
        )

        try:
            message = Message(
                session_id=session.id,
                role=normalized_role,
                content=cleaned_content
            )
            db.add(message)

            # Touch session updated_at
            session.updated_at = func.now()

            await db.commit()
            await db.refresh(message)

            logger.info(
                "Message successfully added",
                extra={"session_id": clean_session_id, "message_id": message.id, "role": message.role}
            )
            return message
        except SQLAlchemyError as exc:
            await db.rollback()
            logger.error(
                "Failed to add message to session '%s': %s",
                clean_session_id,
                exc,
                exc_info=True
            )
            raise SessionServiceError(f"Database error while adding message: {exc}") from exc

    @staticmethod
    async def get_session_messages(
        db: AsyncSession,
        session_id: str
    ) -> List[Message]:
        """
        Retrieves all messages for a session in strict chronological order
        (earliest first).
        Raises SessionNotFoundError if the session does not exist.
        """
        if not session_id or not isinstance(session_id, str) or not session_id.strip():
            raise SessionNotFoundError("A valid session_id must be provided.")

        clean_session_id = session_id.strip()

        # Verify session existence
        session = await SessionService.get_session(db, clean_session_id)
        if session is None:
            logger.warning("Attempted to get messages for non-existent session", extra={"session_id": clean_session_id})
            raise SessionNotFoundError(f"Session '{clean_session_id}' does not exist.")

        logger.debug("Fetching conversation history", extra={"session_id": clean_session_id})

        try:
            stmt = (
                select(Message)
                .where(Message.session_id == clean_session_id)
                .order_by(Message.created_at.asc(), Message.id.asc())
            )
            result = await db.execute(stmt)
            messages = list(result.scalars().all())
            logger.debug(
                "Retrieved conversation history",
                extra={"session_id": clean_session_id, "message_count": len(messages)}
            )
            return messages
        except SQLAlchemyError as exc:
            logger.error(
                "Failed to retrieve messages for session '%s': %s",
                clean_session_id,
                exc,
                exc_info=True
            )
            raise SessionServiceError(f"Database error while fetching messages: {exc}") from exc

    @staticmethod
    async def update_session_title(
        db: AsyncSession,
        session_id: str,
        title: str
    ) -> Session:
        """
        Updates the title of an existing chat session.
        """
        if not session_id or not isinstance(session_id, str) or not session_id.strip():
            raise SessionNotFoundError("A valid session_id must be provided.")

        clean_id = session_id.strip()
        clean_title = title.strip() if title and title.strip() else "Untitled Chat"

        session = await SessionService.get_session(db, clean_id)
        if session is None:
            raise SessionNotFoundError(f"Session '{clean_id}' does not exist.")

        try:
            session.title = clean_title
            session.updated_at = func.now()
            await db.commit()
            await db.refresh(session)
            logger.info("Session title updated", extra={"session_id": clean_id, "new_title": clean_title})
            return session
        except SQLAlchemyError as exc:
            await db.rollback()
            logger.error("Failed to update session title for '%s': %s", clean_id, exc, exc_info=True)
            raise SessionServiceError(f"Database error while updating session: {exc}") from exc

    @staticmethod
    async def delete_session(
        db: AsyncSession,
        session_id: str
    ) -> bool:
        """
        Deletes a chat session and all its associated messages (cascaded).
        """
        if not session_id or not isinstance(session_id, str) or not session_id.strip():
            raise SessionNotFoundError("A valid session_id must be provided.")

        clean_id = session_id.strip()
        session = await SessionService.get_session(db, clean_id)
        if session is None:
            raise SessionNotFoundError(f"Session '{clean_id}' does not exist.")

        try:
            await db.delete(session)
            await db.commit()
            logger.info("Session deleted", extra={"session_id": clean_id})
            return True
        except SQLAlchemyError as exc:
            await db.rollback()
            logger.error("Failed to delete session '%s': %s", clean_id, exc, exc_info=True)
            raise SessionServiceError(f"Database error while deleting session: {exc}") from exc


# Functional aliases for convenience
create_session = SessionService.create_session
get_session = SessionService.get_session
list_sessions = SessionService.list_sessions
add_message = SessionService.add_message
get_session_messages = SessionService.get_session_messages
update_session_title = SessionService.update_session_title
delete_session = SessionService.delete_session
