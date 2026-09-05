"""Artifact retrieval endpoint."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.db_models import Artifact
from app.models.schemas import ArtifactResponse

router = APIRouter()


@router.get(
    "/artifacts/{artifact_id}",
    response_model=ArtifactResponse,
    tags=["artifacts"],
)
async def get_artifact(
    artifact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ArtifactResponse:
    """Return a persisted Markdown or HTML artifact by ID."""
    artifact = await db.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "artifact_not_found",
                "message": f"Artifact {artifact_id} does not exist",
            },
        )
    return ArtifactResponse.model_validate(artifact)
