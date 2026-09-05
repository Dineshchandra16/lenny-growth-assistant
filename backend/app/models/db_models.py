"""
app/models/db_models.py
────────────────────────
SQLAlchemy ORM models for all database tables.

Tables defined here (all created at startup via init_db):
  - Session       — chat sessions
  - Message       — ordered messages within a session
  - Artifact      — generated markdown/html artifacts linked to messages
  - TranscriptChunk — embedded podcast transcript chunks (vector populated in Phase 2)

Relationships:
  Session  1──* Message
  Message  1──* Artifact
  TranscriptChunk — standalone (no FK to Message/Session)
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# Session
# ─────────────────────────────────────────────────────────────────────────────
class Session(Base):
    __tablename__ = "sessions"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False, default="New Session")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )

    messages = relationship(
        "Message",
        back_populates="session",
        order_by="Message.created_at",
        cascade="all, delete-orphan",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Message
# ─────────────────────────────────────────────────────────────────────────────
class Message(Base):
    __tablename__ = "messages"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(20), nullable=False)   # "user" | "assistant"
    content = Column(Text, nullable=False)

    # JSONB array of citation objects:
    # [{"episode_title": str, "guest_name": str, "timestamp_ref": str, "score": float}]
    sources = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True, default=None)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    session = relationship("Session", back_populates="messages")
    artifacts = relationship(
        "Artifact",
        back_populates="message",
        cascade="all, delete-orphan",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Artifact
# ─────────────────────────────────────────────────────────────────────────────
class Artifact(Base):
    __tablename__ = "artifacts"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    artifact_type = Column(String(20), nullable=False)  # "markdown" | "html"
    title = Column(String(255), nullable=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    message = relationship("Message", back_populates="artifacts")


# ─────────────────────────────────────────────────────────────────────────────
# TranscriptChunk  (embedding column added in Phase 2 via ALTER TABLE)
# ─────────────────────────────────────────────────────────────────────────────
class TranscriptChunk(Base):
    """
    Stores chunked podcast transcript text.
    The `embedding` vector column is added in Phase 2 once sentence-transformers
    is wired. Declaring the model here now ensures FK integrity is possible
    from the start and the table schema is visible.
    """

    __tablename__ = "transcript_chunks"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    episode_title = Column(String(512), nullable=False)
    guest_name = Column(String(255), nullable=True)
    publish_date = Column(String(50), nullable=True)   # ISO date string
    timestamp_ref = Column(String(100), nullable=True)  # e.g. "00:12:34"
    chunk_text = Column(Text, nullable=False)
    token_count = Column(Integer, nullable=True)
    embedding = Column(
        Vector(384).with_variant(JSON(), "sqlite"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
