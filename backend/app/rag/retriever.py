"""
app/rag/retriever.py
────────────────────
Transcript retriever with cosine similarity search and threshold filtering.

Uses pgvector cosine distance on PostgreSQL, and vector dot-product on test
dialects. Only chunks with similarity score >= threshold are returned.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.db_models import TranscriptChunk
from app.rag.embeddings import EmbeddingService, get_embedding_service

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class RetrievedChunk:
    """A retrieved transcript chunk with source attribution and similarity score."""

    id: uuid.UUID
    episode_title: str
    guest_name: str | None
    publish_date: str | None
    timestamp_ref: str | None
    chunk_text: str
    token_count: int | None
    score: float

    @property
    def citation_label(self) -> str:
        """Formatted citation label e.g., '[Episode: Brian Balfour, 00:15:30]'"""
        guest = self.guest_name or "Guest"
        ref = f", {self.timestamp_ref}" if self.timestamp_ref else ""
        return f"[{self.episode_title}: {guest}{ref}]"


class TranscriptRetriever:
    """Retrieves the most relevant podcast transcript chunks for a user query."""

    def __init__(
        self,
        db: AsyncSession,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        self.db = db
        self.embedding_service = embedding_service or get_embedding_service()

    async def search(
        self,
        query: str,
        top_k: int | None = None,
        threshold: float | None = None,
    ) -> list[RetrievedChunk]:
        """
        Embed the query and retrieve top-K relevant chunks above the similarity threshold.

        Returns an empty list if no chunks meet the relevance threshold.
        """
        k = top_k if top_k is not None else settings.rag_top_k
        thresh = threshold if threshold is not None else settings.rag_similarity_threshold

        clean_query = query.strip()
        if not clean_query:
            return []

        query_embedding = self.embedding_service.embed_query(clean_query)
        dialect = self.db.bind.dialect.name if self.db.bind else "postgresql"

        if dialect == "postgresql":
            return await self._search_pgvector(query_embedding, k, thresh)
        else:
            return await self._search_fallback(query_embedding, k, thresh)

    async def _search_pgvector(
        self,
        query_vec: list[float],
        top_k: int,
        threshold: float,
    ) -> list[RetrievedChunk]:
        """Run pgvector cosine similarity search on PostgreSQL."""
        # Cosine distance operator (<=>): distance = 1 - cosine_similarity
        # similarity = 1.0 - distance
        distance_expr = TranscriptChunk.embedding.cosine_distance(query_vec)
        score_expr = (1.0 - distance_expr).label("score")

        stmt = (
            select(TranscriptChunk, score_expr)
            .where(TranscriptChunk.embedding.is_not(None))
            .where(score_expr >= threshold)
            .order_by(score_expr.desc())
            .limit(top_k)
        )

        result = await self.db.execute(stmt)
        rows = result.all()

        retrieved: list[RetrievedChunk] = []
        for chunk, score in rows:
            retrieved.append(
                RetrievedChunk(
                    id=chunk.id,
                    episode_title=chunk.episode_title,
                    guest_name=chunk.guest_name,
                    publish_date=chunk.publish_date,
                    timestamp_ref=chunk.timestamp_ref,
                    chunk_text=chunk.chunk_text,
                    token_count=chunk.token_count,
                    score=float(score),
                )
            )

        logger.info(
            "Retrieved %d chunks via pgvector (threshold=%.2f, top_k=%d)",
            len(retrieved),
            threshold,
            top_k,
        )
        return retrieved

    async def _search_fallback(
        self,
        query_vec: list[float],
        top_k: int,
        threshold: float,
    ) -> list[RetrievedChunk]:
        """In-memory cosine similarity search (used in SQLite test environments)."""
        stmt = select(TranscriptChunk).where(TranscriptChunk.embedding.is_not(None))
        result = await self.db.execute(stmt)
        chunks = result.scalars().all()

        if not chunks:
            return []

        q_vec = np.array(query_vec, dtype=np.float32)
        q_norm = np.linalg.norm(q_vec)
        if q_norm == 0:
            return []

        scored_chunks: list[tuple[TranscriptChunk, float]] = []

        for chunk in chunks:
            raw_emb = chunk.embedding
            if raw_emb is None:
                continue

            c_vec = np.array(raw_emb, dtype=np.float32)
            c_norm = np.linalg.norm(c_vec)
            if c_norm == 0:
                continue

            similarity = float(np.dot(q_vec, c_vec) / (q_norm * c_norm))
            if similarity >= threshold:
                scored_chunks.append((chunk, similarity))

        scored_chunks.sort(key=lambda x: x[1], reverse=True)
        top_chunks = scored_chunks[:top_k]

        retrieved = [
            RetrievedChunk(
                id=chunk.id,
                episode_title=chunk.episode_title,
                guest_name=chunk.guest_name,
                publish_date=chunk.publish_date,
                timestamp_ref=chunk.timestamp_ref,
                chunk_text=chunk.chunk_text,
                token_count=chunk.token_count,
                score=score,
            )
            for chunk, score in top_chunks
        ]

        logger.info(
            "Retrieved %d chunks via fallback search (threshold=%.2f, top_k=%d)",
            len(retrieved),
            threshold,
            top_k,
        )
        return retrieved

