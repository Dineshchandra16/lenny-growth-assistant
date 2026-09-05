"""
backend/tests/test_api.py
──────────────────────────
Phase 1 integration tests for:
  - GET  /api/health
  - POST /api/sessions
  - GET  /api/sessions/{id}
  - GET  /api/sessions/{bad_id} → 404
  - POST /api/chat  (SSE echo)
  - POST /api/chat  with bad session_id → 404

These tests use an in-memory SQLite database via SQLAlchemy so they
can run without a running PostgreSQL instance.

NOTE: Vector-related tests (Phase 2) and provider tests (Phase 3)
      live in separate test modules.
"""

import asyncio
import json
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import status
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app

# ─────────────────────────────────────────────────────────────────────────────
# Test database — in-memory SQLite (no pgvector, so TranscriptChunk embedding
# column is not tested here; that's Phase 2)
# ─────────────────────────────────────────────────────────────────────────────
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database():
    """Create tables in the test SQLite database once per session."""
    async with test_engine.begin() as conn:
        # SQLite doesn't have pgvector; import models to register them
        from app.models import db_models  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(autouse=True)
async def override_dependency():
    """Override the real DB dependency and session factory with the test DB for every test."""
    import app.database as app_db

    original_session_local = app_db.AsyncSessionLocal
    app_db.AsyncSessionLocal = TestSessionLocal
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()
    app_db.AsyncSessionLocal = original_session_local


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


# ─────────────────────────────────────────────────────────────────────────────
# Health endpoint
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_returns_200(client: AsyncClient):
    resp = await client.get("/api/health")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert "status" in data
    assert "active_provider" in data
    assert "components" in data


@pytest.mark.asyncio
async def test_health_has_database_component(client: AsyncClient):
    resp = await client.get("/api/health")
    data = resp.json()
    assert "database" in data["components"]


# ─────────────────────────────────────────────────────────────────────────────
# Session endpoints
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_session_default_title(client: AsyncClient):
    resp = await client.post("/api/sessions", json={})
    assert resp.status_code == status.HTTP_201_CREATED
    data = resp.json()
    assert data["title"] == "New Session"
    assert "id" in data
    assert data["messages"] == []


@pytest.mark.asyncio
async def test_create_session_custom_title(client: AsyncClient):
    resp = await client.post("/api/sessions", json={"title": "Growth Q&A"})
    assert resp.status_code == status.HTTP_201_CREATED
    assert resp.json()["title"] == "Growth Q&A"


@pytest.mark.asyncio
async def test_get_session_returns_history(client: AsyncClient):
    # Create a session
    create_resp = await client.post("/api/sessions", json={"title": "Test"})
    session_id = create_resp.json()["id"]

    # Fetch it
    get_resp = await client.get(f"/api/sessions/{session_id}")
    assert get_resp.status_code == status.HTTP_200_OK
    data = get_resp.json()
    assert data["id"] == session_id
    assert isinstance(data["messages"], list)


@pytest.mark.asyncio
async def test_get_session_not_found(client: AsyncClient):
    bad_id = str(uuid.uuid4())
    resp = await client.get(f"/api/sessions/{bad_id}")
    assert resp.status_code == status.HTTP_404_NOT_FOUND
    data = resp.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_list_sessions(client: AsyncClient):
    # Create two sessions
    await client.post("/api/sessions", json={"title": "S1"})
    await client.post("/api/sessions", json={"title": "S2"})

    resp = await client.get("/api/sessions")
    assert resp.status_code == status.HTTP_200_OK
    sessions = resp.json()
    assert isinstance(sessions, list)
    assert len(sessions) >= 2
    titles = [s["title"] for s in sessions]
    assert "S1" in titles
    assert "S2" in titles


# ─────────────────────────────────────────────────────────────────────────────
# Chat endpoint
# ─────────────────────────────────────────────────────────────────────────────

async def _collect_sse(resp) -> list[dict]:
    """Parse SSE stream body into a list of event dicts."""
    events = []
    raw = resp.text
    for line in raw.split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            payload = line[len("data: "):]
            try:
                events.append(json.loads(payload))
            except json.JSONDecodeError:
                pass
    return events


@pytest.mark.asyncio
async def test_chat_echoes_message(client: AsyncClient):
    # Create session first
    session_resp = await client.post("/api/sessions", json={})
    session_id = session_resp.json()["id"]

    resp = await client.post(
        "/api/chat",
        json={"session_id": session_id, "message": "Hello world"},
    )
    assert resp.status_code == status.HTTP_200_OK
    assert "text/event-stream" in resp.headers["content-type"]

    events = await _collect_sse(resp)
    # Should have at least one chunk event and a done event
    chunk_events = [e for e in events if e.get("type") == "chunk"]
    done_events = [e for e in events if e.get("type") == "done"]
    assert len(chunk_events) > 0
    assert len(done_events) == 1
    assert "message_id" in done_events[0]


@pytest.mark.asyncio
async def test_chat_with_invalid_session(client: AsyncClient):
    bad_id = str(uuid.uuid4())
    resp = await client.post(
        "/api/chat",
        json={"session_id": bad_id, "message": "Hello"},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_chat_persists_messages(client: AsyncClient):
    """After a chat round-trip, session history should contain user + assistant messages."""
    session_resp = await client.post("/api/sessions", json={})
    session_id = session_resp.json()["id"]

    await client.post(
        "/api/chat",
        json={"session_id": session_id, "message": "Persistence test"},
    )

    session_resp = await client.get(f"/api/sessions/{session_id}")
    messages = session_resp.json()["messages"]
    roles = [m["role"] for m in messages]
    assert "user" in roles
    assert "assistant" in roles


@pytest.mark.asyncio
async def test_chat_empty_message_rejected(client: AsyncClient):
    session_resp = await client.post("/api/sessions", json={})
    session_id = session_resp.json()["id"]

    resp = await client.post(
        "/api/chat",
        json={"session_id": session_id, "message": ""},
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
