import uuid
from datetime import datetime
from typing import List
from sqlalchemy import Column, Integer, String, Text, DateTime, Date, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from app.database import Base

class Episode(Base):
    """
    Represents an episode with its metadata and transcript reference.
    """
    __tablename__ = "episodes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    slug = Column(String(500), unique=True, index=True, nullable=False)
    transcript_path = Column(String(1000), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationship to TranscriptChunk
    chunks = relationship(
        "TranscriptChunk",
        back_populates="episode",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Episode(id={self.id}, title='{self.title}', slug='{self.slug}')>"


class TranscriptChunk(Base):
    """
    Represents an embedded text chunk derived from an episode transcript.
    """
    __tablename__ = "transcript_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    episode_id = Column(
        Integer,
        ForeignKey("episodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationship back to Episode
    episode = relationship(
        "Episode",
        back_populates="chunks"
    )

    def __repr__(self) -> str:
        return f"<TranscriptChunk(id={self.id}, episode_id={self.episode_id}, chunk_index={self.chunk_index})>"


class Session(Base):
    """
    Represents a chat session with an optional title and conversation metadata.
    """
    __tablename__ = "sessions"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    title = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Relationship to Message (cascade delete when a session is removed)
    messages = relationship(
        "Message",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Message.created_at.asc()"
    )

    def __init__(self, **kwargs):
        if "id" not in kwargs or kwargs["id"] is None:
            kwargs["id"] = str(uuid.uuid4())
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<Session(id='{self.id}', title='{self.title}')>"


class Message(Base):
    """
    Represents an individual message exchanged within a chat session.
    """
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        String(36),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    role = Column(String(50), nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Relationship back to Session
    session = relationship(
        "Session",
        back_populates="messages"
    )

    __table_args__ = (
        Index("ix_messages_session_id_created_at", "session_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Message(id={self.id}, session_id='{self.session_id}', role='{self.role}')>"


class TranscriptChunkGemini(Base):
    """
    Represents an embedded text chunk derived from an episode transcript
    stored in the transcript_chunks_gemini table with Gemini embeddings (768 dim).
    """
    __tablename__ = "transcript_chunks_gemini"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    episode_title = Column(Text, nullable=True)
    guest_name = Column(Text, nullable=True)
    publication_date = Column(Date, nullable=True)
    timestamp_ref = Column(Text, nullable=True)
    youtube_url = Column(Text, nullable=True)
    chunk_text = Column(Text, nullable=False)
    embedding = Column(Vector(768), nullable=True)

    def __repr__(self) -> str:
        return f"<TranscriptChunkGemini(id={self.id}, episode_title='{self.episode_title}', guest_name='{self.guest_name}')>"
