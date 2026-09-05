"""
app/database.py
───────────────
Async SQLAlchemy engine + session factory.

All database access MUST go through `get_db` (injected by FastAPI
dependency-injection). Route handlers never import the engine directly.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# ─────────────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────────────
engine = create_async_engine(
    settings.async_database_url,
    echo=settings.app_env == "development",  # SQL query logging in dev
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Detect stale connections
    pool_recycle=3600,   # Recycle connections every hour
)

# ─────────────────────────────────────────────────────────────────────────────
# Session factory
# ─────────────────────────────────────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ─────────────────────────────────────────────────────────────────────────────
# Declarative base — all ORM models inherit from this
# ─────────────────────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI dependency — yields a session, commits on success, rolls back on error
# ─────────────────────────────────────────────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ─────────────────────────────────────────────────────────────────────────────
# Startup helper — creates all tables and enables pgvector extension
# ─────────────────────────────────────────────────────────────────────────────
async def init_db() -> None:
    """Create tables and enable required PostgreSQL extensions."""
    # Import models to register them with Base metadata
    from app.models import db_models  # noqa: F401

    async with engine.begin() as conn:
        # Enable pgvector (idempotent on postgres)
        if engine.dialect.name == "postgresql":
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        
        # Create all tables that don't yet exist (idempotent)
        await conn.run_sync(Base.metadata.create_all)

        # Create HNSW index on vector column for fast cosine similarity search
        if engine.dialect.name == "postgresql":
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_transcript_chunks_embedding_hnsw "
                    "ON transcript_chunks USING hnsw (embedding vector_cosine_ops)"
                )
            )

    logger.info("Database initialised — tables and vector HNSW index ready")


async def check_db_connection() -> bool:
    """Lightweight health check — returns True if DB is reachable."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning("Database health check failed: %s", exc)
        return False
