"""
app/api/chat.py
────────────────
POST /api/chat

Phase 3 implementation: Grounded RAG Chat Streaming.
- Validates request and session existence.
- Persists user message.
- Delegates to stream_grounded_chat service (retrieval -> provider routing -> SSE streaming -> persistence).
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.db_models import Message, Session
from app.models.schemas import ChatRequest
from app.rag.chat_service import stream_grounded_chat

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.post("/chat", tags=["chat"])
async def chat(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    Accept a chat message and stream the grounded assistant response over SSE.
    """
    # 1. Validate session exists
    result = await db.execute(
        select(Session).where(Session.id == body.session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "session_not_found",
                "message": f"Session {body.session_id} does not exist",
            },
        )

    # 2. Persist user message
    user_msg = Message(
        session_id=body.session_id,
        role="user",
        content=body.message,
        sources=None,
    )
    db.add(user_msg)
    await db.commit()

    logger.info(
        "chat_request_initiated",
        session_id=str(body.session_id),
        provider=body.provider,
        mode=body.mode,
    )

    # 3. Stream grounded chat response
    return StreamingResponse(
        stream_grounded_chat(
            session_id=body.session_id,
            user_message=body.message,
            mode=body.mode,
            provider_name=body.provider,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
