"""
app/rag/embeddings.py
─────────────────────
Embedding generation service.

Supports:
- "local": sentence-transformers (default: all-MiniLM-L6-v2, 384 dimensions)
- "ollama": nomic-embed-text (or configured model) via Ollama API

All embeddings are L2-normalized so that inner product equals cosine similarity.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Sequence

import httpx
import numpy as np

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

EMBEDDING_DIMENSION = 384


class EmbeddingService:
    """Service to generate vector embeddings for text chunks and search queries."""

    def __init__(self, provider: str | None = None, model_name: str | None = None) -> None:
        self.provider = provider or settings.embedding_provider
        self.model_name = model_name or settings.embedding_model
        self._model = None

    def _get_local_model(self):
        """Lazy-load the local sentence-transformers model."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading sentence-transformers model: %s", self.model_name)
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed_query(self, text: str) -> list[float]:
        """Generate a normalized embedding vector for a single search query."""
        clean_text = text.strip()
        if not clean_text:
            return [0.0] * EMBEDDING_DIMENSION

        if self.provider == "ollama":
            return self._embed_ollama_single(clean_text)

        # Local sentence-transformers
        model = self._get_local_model()
        vector = model.encode(clean_text, normalize_embeddings=True)
        return vector.tolist()

    def embed_documents(self, texts: Sequence[str], batch_size: int = 32) -> list[list[float]]:
        """Generate normalized embedding vectors for a batch of documents/chunks."""
        if not texts:
            return []

        cleaned = [t.strip() if t.strip() else " " for t in texts]

        if self.provider == "ollama":
            return [self._embed_ollama_single(t) for t in cleaned]

        # Local sentence-transformers
        model = self._get_local_model()
        vectors = model.encode(
            cleaned,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vectors.tolist()

    def _embed_ollama_single(self, text: str) -> list[float]:
        """Fetch embedding from Ollama /api/embeddings endpoint."""
        url = f"{settings.ollama_base_url}/api/embeddings"
        payload = {
            "model": self.model_name if self.model_name != "all-MiniLM-L6-v2" else "nomic-embed-text",
            "prompt": text,
        }
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                raw_vector = data.get("embedding", [])
                # Normalize vector to unit length
                vec = np.array(raw_vector, dtype=np.float32)
                norm = np.linalg.norm(vec)
                if norm > 0:
                    vec = vec / norm
                return vec.tolist()
        except Exception as exc:
            logger.error("Ollama embedding generation failed: %s", type(exc).__name__)
            raise RuntimeError("Ollama embedding generation failed") from exc


@lru_cache(maxsize=1)
def get_embedding_service() -> EmbeddingService:
    """Return singleton EmbeddingService."""
    return EmbeddingService()
