"""
app/api/sessions.py
────────────────────
Session management endpoints:
  POST /api/sessions        — create a new session
  GET  /api/sessions        — list all sessions (newest first)
  GET  /api/sessions/{id}   — fetch session with full message history

Route handlers are thin: validate → call service function → return schema.
No direct ORM usage in handlers; all DB logic lives in the service helpers below.
"""

import logging
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.db_models import Message, Session
from app.models.schemas import (
    MessageResponse,
    SessionCreate,
    SessionResponse,
    SessionSummary,
)

logger = structlog.get_logger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers (thin service layer, same file for Phase 1 simplicity)
# ─────────────────────────────────────────────────────────────────────────────

async def _get_session_or_404(session_id: uuid.UUID, db: AsyncSession) -> Session:
    """Load a session (with messages + artifacts) or raise 404."""
    result = await db.execute(
        select(Session)
        .options(
            selectinload(Session.messages).selectinload(Message.artifacts)
        )
        .where(Session.id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "session_not_found", "message": f"Session {session_id} does not exist"},
        )
    return session


def _session_to_response(session: Session) -> SessionResponse:
    """Map ORM Session → SessionResponse schema."""
    messages = [
        MessageResponse(
            id=msg.id,
            session_id=msg.session_id,
            role=msg.role,
            content=msg.content,
            sources=msg.sources,
            artifacts=[
                {
                    "id": art.id,
                    "artifact_type": art.artifact_type,
                    "title": art.title,
                    "content": art.content,
                    "created_at": art.created_at,
                }
                for art in msg.artifacts
            ],
            created_at=msg.created_at,
        )
        for msg in session.messages
    ]
    return SessionResponse(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=messages,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["sessions"],
)
async def create_session(
    body: SessionCreate,
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    """Create a new chat session."""
    session = Session(title=body.title)
    db.add(session)
    await db.flush()  # get the generated UUID before commit

    log = logger.bind(session_id=str(session.id), title=session.title)
    log.info("session_created")

    return SessionResponse(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=[],
    )


@router.get(
    "/sessions",
    response_model=list[SessionSummary],
    tags=["sessions"],
)
async def list_sessions(db: AsyncSession = Depends(get_db)) -> list[SessionSummary]:
    """Return all sessions ordered by most recently updated."""
    result = await db.execute(
        select(Session).order_by(Session.updated_at.desc())
    )
    sessions = result.scalars().all()
    return [
        SessionSummary(
            id=s.id,
            title=s.title,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in sessions
    ]


@router.get(
    "/sessions/{session_id}",
    response_model=SessionResponse,
    tags=["sessions"],
)
async def get_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    """Return a session with its full ordered message history."""
    session = await _get_session_or_404(session_id, db)
    return _session_to_response(session)
