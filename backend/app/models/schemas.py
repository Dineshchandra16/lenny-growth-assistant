"""
app/models/schemas.py
─────────────────────
Pydantic v2 request/response contracts.

Rules:
- Request models validate incoming data (strict where needed).
- Response models serialize DB objects to JSON.
- No SQLAlchemy objects ever cross the API boundary.
- No raw error tracebacks included in error responses.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ─────────────────────────────────────────────────────────────────────────────
# Shared
# ─────────────────────────────────────────────────────────────────────────────

class SourceCitation(BaseModel):
    """A single source citation attached to an assistant message."""

    episode_title: str
    guest_name: str | None = None
    timestamp_ref: str | None = None
    score: float | None = None  # cosine similarity score


# ─────────────────────────────────────────────────────────────────────────────
# Session
# ─────────────────────────────────────────────────────────────────────────────

class SessionCreate(BaseModel):
    """Body for POST /api/sessions."""

    title: str = Field(default="New Session", max_length=255)


class ArtifactResponse(BaseModel):
    """Artifact embedded in a message response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    artifact_type: Literal["markdown", "html"]
    title: str | None
    content: str
    created_at: datetime


class ArtifactSummary(BaseModel):
    """Artifact metadata included in a completed chat SSE event."""

    artifact_type: Literal["markdown", "html"]
    title: str | None = None


class MessageResponse(BaseModel):
    """A single message as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    role: Literal["user", "assistant"]
    content: str
    sources: list[SourceCitation] | None = None
    artifacts: list[ArtifactResponse] = []
    created_at: datetime


class SessionResponse(BaseModel):
    """Full session with ordered message history."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[MessageResponse] = []


class SessionSummary(BaseModel):
    """Lightweight session list item (no messages)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


# ─────────────────────────────────────────────────────────────────────────────
# Chat
# ─────────────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    """Body for POST /api/chat."""

    session_id: uuid.UUID
    message: str = Field(..., min_length=1, max_length=8000)
    mode: Literal["default", "ship30"] = "default"
    provider: Literal["ollama", "anthropic", "openai"] | None = None
    # If None, falls back to DEFAULT_LLM_PROVIDER env var


# ─────────────────────────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────────────────────────

class ComponentStatus(BaseModel):
    status: Literal["ok", "degraded", "unavailable"]
    detail: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "unavailable"]
    version: str = "1.0.0"
    active_provider: str
    components: dict[str, ComponentStatus]


# ─────────────────────────────────────────────────────────────────────────────
# Structured Error
# ─────────────────────────────────────────────────────────────────────────────

class ErrorDetail(BaseModel):
    """Standard error envelope — never exposes raw tracebacks."""

    error: str           # machine-readable error code / short description
    message: str         # human-readable explanation
    details: dict[str, Any] | None = None
