"""
backend/tests/test_retrieval.py
───────────────────────────────
Phase 2 tests for:
  - EmbeddingService (embedding generation, dimensions, normalization)
  - TranscriptChunker (recursive chunking, token estimation, timestamp tracking)
  - Idempotent ingestion pipeline
  - TranscriptRetriever (similarity ranking, threshold filtering, empty results handling)
  - POST /api/ingest endpoint
"""

import math
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import AsyncGenerator

import numpy as np
import pytest
import pytest_asyncio
from fastapi import status
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.models.db_models import TranscriptChunk
from app.rag.chunker import ParsedTranscript, TranscriptChunker
from app.rag.embeddings import EmbeddingService, get_embedding_service
from app.rag.retriever import TranscriptRetriever
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
    """Create all tables in the SQLite test database."""
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


@pytest.fixture(scope="module")
def embedding_service() -> EmbeddingService:
    return get_embedding_service()


@pytest.fixture
def sample_transcripts_dir():
    temp_dir = Path(tempfile.mkdtemp(prefix="lenny_test_transcripts_"))
    file1 = temp_dir / "elena_verna.md"
    file1.write_text(
        """---
episode_title: "Elena Verna on PLG"
guest_name: "Elena Verna"
publish_date: "2023-04-12"
---

# Elena Verna on PLG

[00:01:00] In B2B product-led growth, Product Qualified Leads (PQLs) are the most critical metric.
A PQL occurs when a team has activated 3 or more collaborators within 7 days.
Product-Led Sales is an accelerator to self-serve, not a gatekeeper.

[00:05:00] Viral loops in B2B work through invitation mechanisms and shared workspace templates.
""",
        encoding="utf-8",
    )

    file2 = temp_dir / "brian_balfour.md"
    file2.write_text(
        """---
episode_title: "Brian Balfour on Four Fits"
guest_name: "Brian Balfour"
publish_date: "2022-11-15"
---

# Brian Balfour on Four Fits

[00:02:00] Product-Market Fit is not enough to build a 100M dollar company.
You need Market-Product Fit, Product-Channel Fit, Channel-Model Fit, and Model-Market Fit.
Retention is the foundation of the growth engine.
""",
        encoding="utf-8",
    )
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Embedding Service Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_embedding_dimensions(embedding_service: EmbeddingService):
    vector = embedding_service.embed_query("Product-Led Growth strategies")
    assert isinstance(vector, list)
    assert len(vector) == 384
    # Check L2 normalization (norm should be ~1.0)
    norm = np.linalg.norm(np.array(vector, dtype=np.float32))
    assert abs(norm - 1.0) < 1e-3


def test_embedding_batch(embedding_service: EmbeddingService):
    texts = [
        "Product-Led Growth and PQL metrics",
        "Retention curves and churn reduction",
        "High-velocity growth experimentation sprints",
    ]
    vectors = embedding_service.embed_documents(texts)
    assert len(vectors) == 3
    for v in vectors:
        assert len(v) == 384
        norm = np.linalg.norm(np.array(v, dtype=np.float32))
        assert abs(norm - 1.0) < 1e-3


def test_embedding_empty_text(embedding_service: EmbeddingService):
    vec = embedding_service.embed_query("")
    assert len(vec) == 384
    assert all(x == 0.0 for x in vec)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Chunker Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_chunker_basic_splitting():
    chunker = TranscriptChunker(chunk_size_tokens=100, chunk_overlap_tokens=20)
    transcript = ParsedTranscript(
        episode_title="Test Episode",
        guest_name="Test Guest",
        publish_date="2023-01-01",
        raw_text="""
        [00:01:00] First segment discussing growth loops and viral mechanisms in detail.
        
        [00:05:00] Second segment discussing pricing and packaging frameworks.
        """,
    )
    chunks = chunker.chunk_transcript(transcript)
    assert len(chunks) > 0
    for chunk in chunks:
        assert chunk.episode_title == "Test Episode"
        assert chunk.guest_name == "Test Guest"
        assert chunk.chunk_text
        assert chunk.token_count > 0


def test_chunker_timestamp_extraction():
    chunker = TranscriptChunker(chunk_size_tokens=200, chunk_overlap_tokens=30)
    transcript = ParsedTranscript(
        episode_title="Timestamp Test",
        guest_name="Guest",
        publish_date="2023-01-01",
        raw_text="[00:14:30] This chunk starts with a distinct timestamp ref.",
    )
    chunks = chunker.chunk_transcript(transcript)
    assert len(chunks) == 1
    assert chunks[0].timestamp_ref == "00:14:30"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Ingestion Pipeline & Idempotency Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_idempotent_ingestion(sample_transcripts_dir: Path, embedding_service: EmbeddingService):
    async with TestSessionLocal() as session:
        # First run: ingest files
        stats1 = await ingest_transcripts_from_dir(sample_transcripts_dir, session, embedding_service)
        assert stats1.episodes_processed == 2
        assert stats1.chunks_added > 0

        # Count stored chunks
        res1 = await session.execute(select(TranscriptChunk))
        count1 = len(res1.scalars().all())
        assert count1 == stats1.chunks_added

        # Second run: re-ingest exact same directory
        stats2 = await ingest_transcripts_from_dir(sample_transcripts_dir, session, embedding_service)
        assert stats2.episodes_processed == 2
        assert stats2.chunks_updated == count1

        # Verify no duplicate rows were created
        res2 = await session.execute(select(TranscriptChunk))
        count2 = len(res2.scalars().all())
        assert count2 == count1


# ─────────────────────────────────────────────────────────────────────────────
# 4. TranscriptRetriever Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_retriever_returns_relevant_chunks(
    sample_transcripts_dir: Path,
    embedding_service: EmbeddingService,
):
    async with TestSessionLocal() as session:
        # Ingest sample data
        await ingest_transcripts_from_dir(sample_transcripts_dir, session, embedding_service)

        retriever = TranscriptRetriever(db=session, embedding_service=embedding_service)

        # Query specific to Elena Verna's PQL topic
        results = await retriever.search(
            query="What is a Product Qualified Lead (PQL) in PLG?",
            top_k=3,
            threshold=0.20,
        )

        assert len(results) > 0
        top_result = results[0]
        assert top_result.guest_name == "Elena Verna"
        assert "PQL" in top_result.chunk_text or "Product Qualified" in top_result.chunk_text
        assert top_result.score >= 0.20
        assert "[Elena Verna on PLG: Elena Verna" in top_result.citation_label


@pytest.mark.asyncio
async def test_retriever_threshold_filtering(
    sample_transcripts_dir: Path,
    embedding_service: EmbeddingService,
):
    async with TestSessionLocal() as session:
        await ingest_transcripts_from_dir(sample_transcripts_dir, session, embedding_service)

        retriever = TranscriptRetriever(db=session, embedding_service=embedding_service)

        # High threshold should filter out weakly-related chunks
        high_thresh_results = await retriever.search(
            query="B2B growth loops",
            top_k=5,
            threshold=0.85,  # Very strict threshold
        )
        for r in high_thresh_results:
            assert r.score >= 0.85


@pytest.mark.asyncio
async def test_retriever_empty_results_on_unrelated_query(
    sample_transcripts_dir: Path,
    embedding_service: EmbeddingService,
):
    async with TestSessionLocal() as session:
        await ingest_transcripts_from_dir(sample_transcripts_dir, session, embedding_service)

        retriever = TranscriptRetriever(db=session, embedding_service=embedding_service)

        # Totally unrelated query with standard threshold
        results = await retriever.search(
            query="How do quantum superconducting qubits maintain phase coherence at millikelvin temperatures?",
            top_k=5,
            threshold=0.50,
        )
        assert len(results) == 0


@pytest.mark.asyncio
async def test_retriever_empty_archive(embedding_service: EmbeddingService):
    """Retriever over an empty database should return empty list gracefully."""
    # Use clean in-memory engine
    empty_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with empty_engine.begin() as conn:
        from app.models import db_models  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)

    empty_sessionmaker = async_sessionmaker(bind=empty_engine, class_=AsyncSession)
    async with empty_sessionmaker() as session:
        retriever = TranscriptRetriever(db=session, embedding_service=embedding_service)
        results = await retriever.search("Any query", top_k=5, threshold=0.10)
        assert results == []


# ─────────────────────────────────────────────────────────────────────────────
# 5. Ingest API Endpoint Test
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ingest_api_endpoint(client: AsyncClient, sample_transcripts_dir: Path):
    resp = await client.post(
        "/api/ingest",
        json={"transcripts_dir": str(sample_transcripts_dir)},
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["status"] == "ok"
    assert data["episodes_processed"] == 2
    assert data["chunks_added"] > 0 or data["chunks_updated"] > 0

