"""
app/api/ingest.py
─────────────────
POST /api/ingest

Triggers transcript ingestion from the configured transcripts folder.
Reports episodes processed and chunk count statistics.
"""

from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from scripts.ingest import ingest_transcripts_from_dir

logger = structlog.get_logger(__name__)
router = APIRouter()


class IngestRequest(BaseModel):
    transcripts_dir: str = "transcripts"


class IngestResponse(BaseModel):
    status: str
    episodes_processed: int
    chunks_added: int
    chunks_updated: int
    chunks_skipped: int


@router.post("/ingest", response_model=IngestResponse, tags=["ingestion"])
async def trigger_ingest(
    body: IngestRequest = IngestRequest(),
    db: AsyncSession = Depends(get_db),
) -> IngestResponse:
    """
    Trigger idempotent transcript ingestion from the specified directory.
    """
    path = Path(body.transcripts_dir)
    # Check both relative to working directory and /app/transcripts for docker
    if not path.is_absolute() and not path.exists():
        alt_path = Path("/app") / body.transcripts_dir
        if alt_path.exists():
            path = alt_path

    try:
        stats = await ingest_transcripts_from_dir(path, db)
        log = logger.bind(
            episodes=stats.episodes_processed,
            added=stats.chunks_added,
            updated=stats.chunks_updated,
        )
        log.info("ingest_completed")

        return IngestResponse(
            status="ok",
            episodes_processed=stats.episodes_processed,
            chunks_added=stats.chunks_added,
            chunks_updated=stats.chunks_updated,
            chunks_skipped=stats.chunks_skipped,
        )
    except Exception as exc:
        logger.exception("ingest_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "ingestion_failed", "message": str(exc)},
        )

