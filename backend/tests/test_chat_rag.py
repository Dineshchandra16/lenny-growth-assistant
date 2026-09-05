"""
backend/tests/test_chat_rag.py
──────────────────────────────
Phase 3 tests for Grounded RAG Chat flow:
- Grounded prompt formatting and citation labels
- Multi-turn history resolution
- SSE streaming with mock LLM provider and source attribution
- Insufficient information fallback path
"""

import json
import tempfile
import uuid
from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import status
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.models.db_models import Message, Session
from app.providers.base import ProviderUnavailableError
from app.rag.embeddings import get_embedding_service
from app.rag.prompt import (
    INSUFFICIENT_INFORMATION_PHRASE,
    build_rag_system_prompt,
    format_messages_with_history,
)
from app.rag.retriever import RetrievedChunk
from app.skills.artifact_parser import extract_artifacts
from scripts.ingest import ingest_transcripts_from_dir

from sqlalchemy.pool import StaticPool

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
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


@pytest_asyncio.fixture(scope="module", autouse=True)
async def setup_database():
    async with test_engine.begin() as conn:
        from app.models import db_models  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(autouse=True)
async def override_dependency():
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


@pytest_asyncio.fixture(scope="module", autouse=True)
async def seed_transcript_data(setup_database):
    """Seed test SQLite DB with realistic transcript chunks."""
    temp_dir = Path(tempfile.mkdtemp(prefix="lenny_chat_test_"))
    file_path = temp_dir / "elena_verna.md"
    file_path.write_text(
        """---
episode_title: "Elena Verna on PLG"
guest_name: "Elena Verna"
publish_date: "2023-04-12"
---

# Elena Verna on PLG

[00:01:20] A Product Qualified Lead (PQL) occurs when a workspace activates 3 or more users in 7 days.
[00:05:30] Product-Led Sales is an accelerator to self-serve monetization, not a gatekeeper.
""",
        encoding="utf-8",
    )
    async with TestSessionLocal() as session:
        await ingest_transcripts_from_dir(temp_dir, session, get_embedding_service())


async def _collect_sse_events(response) -> list[dict]:
    events = []
    for line in response.text.split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            payload = line[len("data: "):]
            try:
                events.append(json.loads(payload))
            except json.JSONDecodeError:
                pass
    return events


# ─────────────────────────────────────────────────────────────────────────────
# 1. Prompt & History Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_build_rag_system_prompt():
    chunk = RetrievedChunk(
        id=uuid.uuid4(),
        episode_title="Elena Verna on PLG",
        guest_name="Elena Verna",
        publish_date="2023-04-12",
        timestamp_ref="00:01:20",
        chunk_text="A Product Qualified Lead (PQL) threshold is 3 collaborators.",
        token_count=15,
        score=0.88,
    )
    prompt = build_rag_system_prompt([chunk])
    assert "Elena Verna" in prompt
    assert "[Elena Verna on PLG: Elena Verna, 00:01:20]" in prompt
    assert INSUFFICIENT_INFORMATION_PHRASE in prompt


def test_format_messages_with_history():
    history = [
        {"role": "user", "content": "What is PLG?"},
        {"role": "assistant", "content": "Product-Led Growth is..."},
    ]
    messages = format_messages_with_history(history, "How do you measure PQLs?")
    assert len(messages) == 3
    assert messages[0]["content"] == "What is PLG?"
    assert messages[1]["content"] == "Product-Led Growth is..."
    assert messages[2]["content"] == "How do you measure PQLs?"


def test_extracts_markdown_and_html_artifacts():
    response = (
        "Here are the deliverables.\n"
        '<artifact type="markdown" title="Plan"># Growth plan\n\n- Test</artifact>\n'
        '<artifact type="html" title="Preview"><script>alert(1)</script><h1>Preview</h1></artifact>'
    )

    cleaned, artifacts = extract_artifacts(response)

    assert cleaned == "Here are the deliverables."
    assert [(item.artifact_type, item.title) for item in artifacts] == [
        ("markdown", "Plan"),
        ("html", "Preview"),
    ]
    assert artifacts[0].content == "# Growth plan\n\n- Test"
    assert "<script>alert(1)</script>" in artifacts[1].content


# ─────────────────────────────────────────────────────────────────────────────
# 2. Grounded Chat SSE Streaming & Persistence Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_grounded_rag_stream(client: AsyncClient):
    # 1. Create a new session
    session_resp = await client.post("/api/sessions", json={"title": "RAG Test"})
    session_id = session_resp.json()["id"]

    # 2. Mock LLM provider to stream answer with citation
    mock_tokens = [
        "In B2B PLG, a PQL is defined by workspace activation ",
        "[Elena Verna on PLG: Elena Verna, 00:01:20].",
    ]

    async def mock_stream_chat(*args, **kwargs):
        for tok in mock_tokens:
            yield tok

    with patch("app.providers.ollama_provider.OllamaProvider.stream_chat", side_effect=mock_stream_chat):
        resp = await client.post(
            "/api/chat",
            json={
                "session_id": session_id,
                "message": "What is a Product Qualified Lead (PQL)?",
                "provider": "ollama",
            },
        )

        assert resp.status_code == status.HTTP_200_OK
        events = await _collect_sse_events(resp)

        # Verify chunks received
        chunks = [e for e in events if e.get("type") == "chunk"]
        assert len(chunks) == len(mock_tokens)

        # Verify done event contains sources
        done_events = [e for e in events if e.get("type") == "done"]
        assert len(done_events) == 1
        sources = done_events[0].get("sources", [])
        assert len(sources) > 0
        assert sources[0]["guest_name"] == "Elena Verna"
        assert sources[0]["episode_title"] == "Elena Verna on PLG"

    # 3. Verify session history persistence
    hist_resp = await client.get(f"/api/sessions/{session_id}")
    hist_data = hist_resp.json()
    assert len(hist_data["messages"]) == 2
    assistant_msg = [m for m in hist_data["messages"] if m["role"] == "assistant"][0]
    assert "In B2B PLG, a PQL" in assistant_msg["content"]
    assert len(assistant_msg["sources"]) > 0


@pytest.mark.asyncio
async def test_chat_insufficient_information_fallback(client: AsyncClient):
    """When query has zero relevance to archive, system must respond with exact fallback phrase."""
    session_resp = await client.post("/api/sessions", json={"title": "Fallback Test"})
    session_id = session_resp.json()["id"]

    resp = await client.post(
        "/api/chat",
        json={
            "session_id": session_id,
            "message": "How do you build a nuclear fission reactor with thorium salts?",
            "provider": "ollama",
        },
    )

    assert resp.status_code == status.HTTP_200_OK
    events = await _collect_sse_events(resp)

    chunk_texts = [e.get("content", "") for e in events if e.get("type") == "chunk"]
    full_text = "".join(chunk_texts)
    assert INSUFFICIENT_INFORMATION_PHRASE in full_text

    done_events = [e for e in events if e.get("type") == "done"]
    assert len(done_events) == 1
    assert done_events[0]["sources"] == []


@pytest.mark.asyncio
async def test_chat_follow_up_with_session_history(client: AsyncClient):
    session_resp = await client.post("/api/sessions", json={"title": "Multi-turn Test"})
    session_id = session_resp.json()["id"]

    # Turn 1
    async def mock_stream_1(*args, **kwargs):
        yield "PQLs require 3 active collaborators."

    with patch("app.providers.ollama_provider.OllamaProvider.stream_chat", side_effect=mock_stream_1):
        await client.post(
            "/api/chat",
            json={"session_id": session_id, "message": "What is a PQL?", "provider": "ollama"},
        )

    # Turn 2: Follow-up referencing "that threshold"
    captured_messages = []

    async def mock_stream_2(*args, **kwargs):
        captured_messages.extend(kwargs.get("messages", []))
        yield "Product-Led Sales reps reach out once crossed."

    with patch("app.providers.ollama_provider.OllamaProvider.stream_chat", side_effect=mock_stream_2):
        await client.post(
            "/api/chat",
            json={"session_id": session_id, "message": "When should sales reach out after that?", "provider": "ollama"},
        )

    # Verify history was forwarded to provider
    roles = [m["role"] for m in captured_messages]
    assert "user" in roles
    assert "assistant" in roles
    user_contents = [m["content"] for m in captured_messages if m["role"] == "user"]
    assert "What is a PQL?" in user_contents
    assert "When should sales reach out after that?" in user_contents


@pytest.mark.asyncio
async def test_chat_persists_and_retrieves_artifacts(client: AsyncClient):
    session_resp = await client.post("/api/sessions", json={"title": "Artifacts"})
    session_id = session_resp.json()["id"]

    async def mock_artifact_stream(*args, **kwargs):
        yield (
            "Here is the result.\n"
            '<artifact type="markdown" title="Experiment plan"># Plan\n\n- Measure activation</artifact>'
        )

    with patch(
        "app.providers.ollama_provider.OllamaProvider.stream_chat",
        side_effect=mock_artifact_stream,
    ):
        response = await client.post(
            "/api/chat",
            json={
                "session_id": session_id,
                "message": "What is a Product Qualified Lead (PQL)?",
                "provider": "ollama",
            },
        )

    events = await _collect_sse_events(response)
    assert events[-1]["artifacts"] == [
        {"artifact_type": "markdown", "title": "Experiment plan"}
    ]

    session = (await client.get(f"/api/sessions/{session_id}")).json()
    assistant = [item for item in session["messages"] if item["role"] == "assistant"][0]
    assert assistant["content"] == "Here is the result."
    assert len(assistant["artifacts"]) == 1
    artifact = assistant["artifacts"][0]
    assert artifact["artifact_type"] == "markdown"
    assert artifact["content"] == "# Plan\n\n- Measure activation"

    artifact_response = await client.get(f"/api/artifacts/{artifact['id']}")
    assert artifact_response.status_code == 200
    assert artifact_response.json()["id"] == artifact["id"]

    missing_response = await client.get(f"/api/artifacts/{uuid.uuid4()}")
    assert missing_response.status_code == 404


@pytest.mark.asyncio
async def test_provider_failure_is_safe_and_streamed_as_error(client: AsyncClient):
    session_resp = await client.post("/api/sessions", json={"title": "Provider failure"})
    session_id = session_resp.json()["id"]

    async def failing_stream(*args, **kwargs):
        raise ProviderUnavailableError("internal endpoint token should not be exposed")
        yield  # pragma: no cover

    with patch(
        "app.providers.ollama_provider.OllamaProvider.stream_chat",
        side_effect=failing_stream,
    ):
        response = await client.post(
            "/api/chat",
            json={
                "session_id": session_id,
                "message": "What is a Product Qualified Lead (PQL)?",
                "provider": "ollama",
            },
        )

    events = await _collect_sse_events(response)
    errors = [event for event in events if event.get("type") == "error"]
    assert errors
    assert "internal endpoint token" not in response.text
    assert "currently unavailable" in response.text
