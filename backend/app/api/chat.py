"""
app/api/chat.py
────────────────
POST /api/chat

Phase 1 implementation: SSE echo stub.
- Validates the request (session exists, message non-empty).
- Persists the user message to the database.
- Streams an echo response over Server-Sent Events (SSE).
- Persists the assistant echo reply.

In Phase 3 this handler will be extended to call the provider router
and the RAG retrieval layer. The SSE framing and persistence logic
defined here will remain unchanged.

SSE format (text/event-stream):
  data: {"type": "chunk", "content": "...", "done": false}\n\n
  ...
  data: {"type": "done", "message_id": "...", "sources": []}\n\n
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.db_models import Message, Session
from app.models.schemas import ChatRequest

logger = structlog.get_logger(__name__)
router = APIRouter()
settings = get_settings()


def _sse_event(data: dict) -> str:
    """Format a dict as a Server-Sent Event data line."""
    return f"data: {json.dumps(data)}\n\n"


async def _echo_stream(user_message: str, provider: str):
    """
    Phase 1 stub: streams the user message back word-by-word
    so the frontend SSE hook can be fully exercised.
    Replace this in Phase 3 with real provider calls.
    """
    prefix = f"[{provider.upper()} — Phase 1 echo] "
    full_response = prefix + user_message

    for word in full_response.split():
        yield word + " "
        await asyncio.sleep(0.04)  # simulate token streaming


@router.post("/chat", tags=["chat"])
async def chat(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    Accept a chat message and stream the assistant reply over SSE.

    The active LLM provider can be overridden per-request via the `provider`
    field; otherwise `DEFAULT_LLM_PROVIDER` env var is used.
    """
    # ── Validate session exists ───────────────────────────────────────────────
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

    # ── Persist user message ──────────────────────────────────────────────────
    user_msg = Message(
        session_id=body.session_id,
        role="user",
        content=body.message,
        sources=None,
    )
    db.add(user_msg)
    await db.commit()

    active_provider = body.provider or settings.default_llm_provider

    log = logger.bind(
        session_id=str(body.session_id),
        provider=active_provider,
        mode=body.mode,
    )
    log.info("chat_request_received")

    # ── SSE generator ─────────────────────────────────────────────────────────
    async def event_stream():
        from app.database import AsyncSessionLocal

        accumulated = []

        async for token in _echo_stream(body.message, active_provider):
            accumulated.append(token)
            yield _sse_event({"type": "chunk", "content": token, "done": False})

        full_content = "".join(accumulated)

        # Persist assistant reply using AsyncSessionLocal
        async with AsyncSessionLocal() as stream_db:
            assistant_msg = Message(
                session_id=body.session_id,
                role="assistant",
                content=full_content,
                sources=None,
            )
            stream_db.add(assistant_msg)

            # Bump session.updated_at
            session_obj = await stream_db.get(Session, body.session_id)
            if session_obj:
                session_obj.updated_at = datetime.now(timezone.utc)

            await stream_db.commit()
            msg_id = str(assistant_msg.id)

        log.info("chat_response_complete", message_id=msg_id, tokens=len(accumulated))
        yield _sse_event({"type": "done", "message_id": msg_id, "sources": []})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
