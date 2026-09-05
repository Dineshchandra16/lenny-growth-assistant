"""
app/api/health.py
──────────────────
GET /api/health

Reports the operational status of:
  - PostgreSQL (can we query the database?)
  - Ollama (is the configured endpoint reachable?)
  - Vector index (does the transcript_chunks table exist with rows?)
  - Active LLM provider configuration

Returns HTTP 200 with status "ok", "degraded", or "unavailable".
Never raises a 500 — failure of a component is reported inside the payload.
"""

import logging

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.schemas import ComponentStatus, HealthResponse

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


async def _check_database(db: AsyncSession) -> ComponentStatus:
    try:
        await db.execute(text("SELECT 1"))
        return ComponentStatus(status="ok")
    except Exception as exc:
        logger.warning("DB health check failed: %s", exc)
        return ComponentStatus(status="unavailable", detail=str(exc))


async def _check_ollama() -> ComponentStatus:
    """Ping Ollama's /api/tags endpoint to verify it's running."""
    url = f"{settings.ollama_base_url}/api/tags"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return ComponentStatus(status="ok")
            return ComponentStatus(
                status="degraded",
                detail=f"Ollama returned HTTP {resp.status_code}",
            )
    except Exception as exc:
        return ComponentStatus(
            status="unavailable",
            detail=f"Ollama unreachable at {settings.ollama_base_url}: {type(exc).__name__}",
        )


async def _check_vector_index(db: AsyncSession) -> ComponentStatus:
    """Check if transcript_chunks table exists and has been indexed."""
    try:
        result = await db.execute(
            text("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'transcript_chunks'")
        )
        exists = result.scalar() == 1
        if not exists:
            return ComponentStatus(status="unavailable", detail="transcript_chunks table not found")

        count_result = await db.execute(text("SELECT COUNT(*) FROM transcript_chunks"))
        count = count_result.scalar() or 0
        if count == 0:
            return ComponentStatus(
                status="degraded",
                detail="transcript_chunks table exists but has no data — run the ingestion script",
            )
        return ComponentStatus(status="ok", detail=f"{count} chunks indexed")
    except Exception as exc:
        return ComponentStatus(status="unavailable", detail=str(exc))


@router.get("/health", response_model=HealthResponse, tags=["ops"])
async def health_check(db: AsyncSession = Depends(get_db)) -> HealthResponse:
    """
    Operational health check.

    Returns the status of each system component and the active LLM provider.
    Safe to call from load-balancers; never leaks secrets or stack traces.
    """
    db_status = await _check_database(db)
    ollama_status = await _check_ollama()
    vector_status = await _check_vector_index(db)

    components = {
        "database": db_status,
        "ollama": ollama_status,
        "vector_index": vector_status,
    }

    # Overall status = worst component
    statuses = [c.status for c in components.values()]
    if all(s == "ok" for s in statuses):
        overall = "ok"
    elif any(s == "unavailable" for s in statuses):
        overall = "degraded"  # system still runs without vector index / ollama
    else:
        overall = "degraded"

    # If DB is unavailable the system is truly unavailable
    if db_status.status == "unavailable":
        overall = "unavailable"

    active_provider = settings.default_llm_provider

    logger.info(
        "Health check completed",
        extra={"overall": overall, "provider": active_provider},
    )

    return HealthResponse(
        status=overall,
        active_provider=active_provider,
        components=components,
    )
