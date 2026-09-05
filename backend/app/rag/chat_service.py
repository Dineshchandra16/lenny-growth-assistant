"""
app/rag/chat_service.py
───────────────────────
Service orchestrating grounded RAG Q&A, multi-turn context resolution,
LLM provider streaming, and conversation persistence.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import app.database as database
from app.config import get_settings
from app.models.db_models import Artifact, Message, Session
from app.providers.base import (
    LLMProviderError,
    ProviderAuthError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    user_facing_provider_error,
)
from app.providers.router import get_provider
from app.rag.embeddings import get_embedding_service
from app.rag.prompt import (
    INSUFFICIENT_INFORMATION_PHRASE,
    build_rag_system_prompt,
    format_messages_with_history,
)
from app.rag.retriever import TranscriptRetriever
from app.skills.ship30_writer import (
    build_ship30_system_prompt,
    validate_ship30_essay,
)
from app.skills.artifact_parser import extract_artifacts

logger = structlog.get_logger(__name__)
settings = get_settings()


def _sse_event(data: dict) -> str:
    """Format a python dict as a Server-Sent Event string."""
    return f"data: {json.dumps(data)}\n\n"


async def stream_grounded_chat(
    session_id: uuid.UUID,
    user_message: str,
    mode: str = "default",
    provider_name: str | None = None,
    db: AsyncSession | None = None,
) -> AsyncGenerator[str, None]:
    """
    Executes grounded RAG retrieval, invokes the selected LLM provider,
    streams tokens via SSE, and persists the turn in PostgreSQL.
    """
    active_provider_name = provider_name or settings.default_llm_provider
    log = logger.bind(
        session_id=str(session_id),
        provider=active_provider_name,
        mode=mode,
    )

    # 1–2. Fetch history and retrieve context. Fail as an SSE error rather than
    # leaving the client with a broken stream if the database or embedder fails.
    try:
        history_messages: list[dict[str, str]] = []
        async with database.AsyncSessionLocal() as read_db:
            session_obj = await read_db.get(
                Session,
                session_id,
                options=[selectinload(Session.messages)],
            )
            if session_obj:
                for m in session_obj.messages:
                    history_messages.append({"role": m.role, "content": m.content})

        async with database.AsyncSessionLocal() as search_db:
            retriever = TranscriptRetriever(
                db=search_db,
                embedding_service=get_embedding_service(),
            )
            chunks = await retriever.search(
                query=user_message,
                top_k=settings.rag_top_k,
                threshold=settings.rag_similarity_threshold,
            )
    except Exception:
        log.exception("rag_retrieval_failed")
        yield _sse_event({
            "type": "error",
            "code": "retrieval_failed",
            "message": "The transcript archive is temporarily unavailable. Please try again.",
        })
        return

    log.info("rag_retrieval_complete", chunks_count=len(chunks))

    # Format sources for metadata persistence
    sources_payload = [
        {
            "episode_title": c.episode_title,
            "guest_name": c.guest_name,
            "timestamp_ref": c.timestamp_ref,
            "score": round(c.score, 4),
        }
        for c in chunks
    ]

    # 3. Check for insufficient context
    if not chunks:
        # Fallback: Not enough information in archive
        fallback_text = INSUFFICIENT_INFORMATION_PHRASE
        yield _sse_event({"type": "chunk", "content": fallback_text, "done": False})

        async with database.AsyncSessionLocal() as write_db:
            assistant_msg = Message(
                session_id=session_id,
                role="assistant",
                content=fallback_text,
                sources=[],
            )
            write_db.add(assistant_msg)
            s_obj = await write_db.get(Session, session_id)
            if s_obj:
                s_obj.updated_at = datetime.now(timezone.utc)
            await write_db.commit()
            msg_id = str(assistant_msg.id)

        log.info("insufficient_information_returned", message_id=msg_id)
        yield _sse_event({"type": "done", "message_id": msg_id, "sources": []})
        return

    # 4. Construct grounded system prompt & conversation history payload
    system_prompt = (
        build_ship30_system_prompt(chunks)
        if mode == "ship30"
        else build_rag_system_prompt(chunks)
    )
    messages_payload = format_messages_with_history(history_messages, user_message)

    # 5. Route to configured LLM Provider
    try:
        provider = get_provider(active_provider_name)
    except Exception as exc:
        log.exception("provider_init_failed", error_type=type(exc).__name__)
        yield _sse_event({
            "type": "error",
            "code": "provider_initialization_failed",
            "message": "The selected provider could not be initialized. Please check its configuration.",
        })
        return

    accumulated_tokens: list[str] = []
    call_started = time.monotonic()
    log.info(
        "provider_call_started",
        model=provider.model_name,
        message_count=len(messages_payload),
    )
    try:
        async for token in provider.stream_chat(
            messages=messages_payload,
            system_prompt=system_prompt,
            temperature=0.2,
        ):
            accumulated_tokens.append(token)
            yield _sse_event({"type": "chunk", "content": token, "done": False})

    except (ProviderUnavailableError, ProviderAuthError, ProviderTimeoutError) as p_err:
        log.warning(
            "provider_call_failed",
            error_type=type(p_err).__name__,
            duration_ms=round((time.monotonic() - call_started) * 1000),
        )
        err_content = user_facing_provider_error(active_provider_name, p_err)
        yield _sse_event({
            "type": "error",
            "code": type(p_err).__name__,
            "message": err_content,
        })
        yield _sse_event({"type": "chunk", "content": err_content, "done": False})
        accumulated_tokens.append(err_content)
    except Exception as exc:
        log.exception(
            "provider_call_failed",
            error_type=type(exc).__name__,
            duration_ms=round((time.monotonic() - call_started) * 1000),
        )
        err_content = user_facing_provider_error(active_provider_name, exc)
        yield _sse_event({
            "type": "error",
            "code": "provider_error",
            "message": err_content,
        })
        yield _sse_event({"type": "chunk", "content": err_content, "done": False})
        accumulated_tokens.append(err_content)
    else:
        log.info(
            "provider_call_completed",
            model=provider.model_name,
            duration_ms=round((time.monotonic() - call_started) * 1000),
            token_count=len(accumulated_tokens),
        )

    full_response = "".join(accumulated_tokens).strip()
    display_response, extracted_artifacts = extract_artifacts(full_response)

    if mode == "ship30":
        validation = validate_ship30_essay(
            display_response,
            [chunk.citation_label for chunk in chunks],
        )
        if not validation.valid:
            display_response = (
                "The Ship 30 for 30 essay failed validation and was not returned. "
                + " ".join(validation.errors)
            )
            extracted_artifacts = []
            log.warning(
                "ship30_validation_failed",
                word_count=validation.word_count,
                errors=validation.errors,
            )

    # 6. Persist assistant message with cited sources
    try:
        async with database.AsyncSessionLocal() as persist_db:
            assistant_msg = Message(
                session_id=session_id,
                role="assistant",
                content=display_response,
                sources=sources_payload,
            )
            persist_db.add(assistant_msg)
            await persist_db.flush()
            for extracted in extracted_artifacts:
                persist_db.add(
                    Artifact(
                        message_id=assistant_msg.id,
                        artifact_type=extracted.artifact_type,
                        title=extracted.title,
                        content=extracted.content,
                    )
                )
            s_obj = await persist_db.get(Session, session_id)
            if s_obj:
                s_obj.updated_at = datetime.now(timezone.utc)
            await persist_db.commit()
            msg_id = str(assistant_msg.id)
    except Exception:
        log.exception("chat_persistence_failed")
        yield _sse_event({
            "type": "error",
            "code": "persistence_failed",
            "message": "The response was generated but could not be saved. Please try again.",
        })
        return

    log.info(
        "grounded_chat_complete",
        message_id=msg_id,
        sources_count=len(sources_payload),
    )
    yield _sse_event({
        "type": "done",
        "message_id": msg_id,
        "sources": sources_payload,
        "artifacts": [
            {
                "artifact_type": extracted.artifact_type,
                "title": extracted.title,
            }
            for extracted in extracted_artifacts
        ],
    })
