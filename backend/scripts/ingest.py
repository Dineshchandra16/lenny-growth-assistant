"""
backend/scripts/ingest.py
──────────────────────────
Transcript ingestion pipeline.

Parses markdown/txt transcript files, extracts metadata, splits into chunks,
generates embeddings, and stores chunks in PostgreSQL with pgvector HNSW index.

Idempotent: Running multiple times replaces chunks for the episode rather than
creating duplicates.

Usage:
    python scripts/ingest.py --transcripts-dir transcripts/
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import sys
from pathlib import Path
from typing import NamedTuple

# Add backend directory to path if run as standalone script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import AsyncSessionLocal, init_db
from app.models.db_models import TranscriptChunk
from app.rag.chunker import ParsedTranscript, TranscriptChunker
from app.rag.embeddings import EmbeddingService, get_embedding_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ingest")
settings = get_settings()


class IngestionStats(NamedTuple):
    episodes_processed: int
    chunks_added: int
    chunks_updated: int
    chunks_skipped: int


def parse_transcript_file(file_path: Path) -> ParsedTranscript:
    """Parse metadata from YAML frontmatter or markdown header."""
    content = file_path.read_text(encoding="utf-8")

    episode_title = file_path.stem.replace("_", " ").title()
    guest_name = None
    publish_date = None

    # Check for frontmatter
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
    if fm_match:
        frontmatter, raw_text = fm_match.group(1), fm_match.group(2)
        for line in frontmatter.splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                key = key.strip().lower()
                val = val.strip().strip('"').strip("'")
                if key == "episode_title":
                    episode_title = val
                elif key == "guest_name":
                    guest_name = val
                elif key == "publish_date":
                    publish_date = val
    else:
        raw_text = content
        # Check first H1 header for title
        h1_match = re.search(r"^#\s+(.*)$", raw_text, re.MULTILINE)
        if h1_match:
            episode_title = h1_match.group(1).strip()

    return ParsedTranscript(
        episode_title=episode_title,
        guest_name=guest_name,
        publish_date=publish_date,
        raw_text=raw_text,
    )


async def ingest_transcripts_from_dir(
    transcripts_dir: Path,
    db: AsyncSession,
    embedding_service: EmbeddingService | None = None,
) -> IngestionStats:
    """Ingest all transcript files in a directory idempotently."""
    embedder = embedding_service or get_embedding_service()
    chunker = TranscriptChunker(
        chunk_size_tokens=settings.chunk_size,
        chunk_overlap_tokens=settings.chunk_overlap,
    )

    if not transcripts_dir.exists():
        logger.warning("Transcripts directory does not exist: %s", transcripts_dir)
        return IngestionStats(0, 0, 0, 0)

    files = [
        p for p in transcripts_dir.iterdir()
        if p.is_file() and p.suffix.lower() in (".md", ".txt")
    ]

    if not files:
        logger.warning("No .md or .txt files found in %s", transcripts_dir)
        return IngestionStats(0, 0, 0, 0)

    episodes_count = 0
    total_added = 0
    total_updated = 0

    for file_path in files:
        logger.info("Processing transcript file: %s", file_path.name)
        parsed = parse_transcript_file(file_path)
        chunks = chunker.chunk_transcript(parsed)

        if not chunks:
            logger.warning("No chunks produced for file: %s", file_path.name)
            continue

        # Check existing chunks for idempotency
        existing_res = await db.execute(
            select(TranscriptChunk).where(TranscriptChunk.episode_title == parsed.episode_title)
        )
        existing_chunks = existing_res.scalars().all()
        is_update = len(existing_chunks) > 0

        # Remove previous chunks for this episode to prevent duplicates
        if is_update:
            await db.execute(
                delete(TranscriptChunk).where(TranscriptChunk.episode_title == parsed.episode_title)
            )

        # Batch compute embeddings
        texts_to_embed = [c.chunk_text for c in chunks]
        embeddings = embedder.embed_documents(texts_to_embed, batch_size=32)

        for chunk_item, embedding in zip(chunks, embeddings):
            db_chunk = TranscriptChunk(
                episode_title=chunk_item.episode_title,
                guest_name=chunk_item.guest_name,
                publish_date=chunk_item.publish_date,
                timestamp_ref=chunk_item.timestamp_ref,
                chunk_text=chunk_item.chunk_text,
                token_count=chunk_item.token_count,
                embedding=embedding,
            )
            db.add(db_chunk)

        await db.commit()
        episodes_count += 1

        if is_update:
            total_updated += len(chunks)
            logger.info("Updated %d chunks for '%s'", len(chunks), parsed.episode_title)
        else:
            total_added += len(chunks)
            logger.info("Added %d chunks for '%s'", len(chunks), parsed.episode_title)

    return IngestionStats(
        episodes_processed=episodes_count,
        chunks_added=total_added,
        chunks_updated=total_updated,
        chunks_skipped=0,
    )


async def main_async(transcripts_dir: Path):
    await init_db()
    async with AsyncSessionLocal() as session:
        stats = await ingest_transcripts_from_dir(transcripts_dir, session)
        logger.info(
            "Ingestion completed: %d episodes processed, %d chunks added, %d updated",
            stats.episodes_processed,
            stats.chunks_added,
            stats.chunks_updated,
        )


def main():
    parser = argparse.ArgumentParser(description="Ingest podcast transcripts into pgvector")
    parser.add_argument(
        "--transcripts-dir",
        type=Path,
        default=Path("transcripts"),
        help="Directory containing transcript markdown or txt files",
    )
    args = parser.parse_args()
    asyncio.run(main_async(args.transcripts_dir))


if __name__ == "__main__":
    main()
