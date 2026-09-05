# Phase 2 — Ingestion & Retrieval: Agent Transcript

**Phase:** 2  
**Date:** 2026-09-05  
**Status:** Complete

---

## Objective

Implement Phase 2 per specification Section 10:
- Transcript download / sample generation script with realistic metadata and timestamp references (`scripts/download_transcripts.py`).
- Recursive character splitting chunker with token estimation and timestamp tracking (`app/rag/chunker.py`).
- Embedding generation service (`app/rag/embeddings.py`) supporting normalized `sentence-transformers` (`all-MiniLM-L6-v2`, 384 dimensions) and Ollama.
- PostgreSQL `pgvector` Vector(384) column and HNSW index on `transcript_chunks` (`app/models/db_models.py`, `app/database.py`).
- Idempotent ingestion pipeline script (`scripts/ingest.py`) and API endpoint (`POST /api/ingest`).
- `TranscriptRetriever` (`app/rag/retriever.py`) with cosine similarity search, threshold-based filtering, and empty-result handling.
- Automated pytest test suite (`tests/test_retrieval.py`) covering chunking, embeddings, idempotent ingestion, and retrieval.

---

## Decisions Made

### 1. Embedding Model & Dimension
**Decision:** Pinned to `sentence-transformers/all-MiniLM-L6-v2` with 384-dimensional normalized vectors.  
**Rationale:** Fast inference (< 100ms CPU), low memory footprint, and strong semantic retrieval performance on English technical content. Normalizing all vectors during embedding generation guarantees cosine similarity equals dot product.

### 2. Recursive Chunker with Timestamp Association
**Decision:** Chunker splits along `\n\n` -> `\n` -> sentence boundaries -> words, aiming for 600 tokens with 100-token overlap, and scans for regex timestamps `[HH:MM:SS]` to attach to each chunk.  
**Rationale:** Ensures paragraphs and thoughts aren't cut mid-sentence while maintaining precise source attribution back to the audio timestamp.

### 3. Cross-Dialect Vector Storage for Testability
**Decision:** `TranscriptChunk.embedding` uses `Vector(384).with_variant(JSON(), "sqlite")`.  
**Rationale:** Allows fast in-memory SQLite unit testing without requiring a live PostgreSQL instance for every test run, while creating true `vector(384)` columns in PostgreSQL production.

### 4. Idempotent Ingestion Strategy
**Decision:** Ingestion clears previous chunks for an `episode_title` within a transaction before inserting updated chunks.  
**Rationale:** Re-running ingestion refreshes the archive without creating duplicate chunks or orphan vectors.

---

## Files Created

- `backend/app/rag/embeddings.py` — Embedding generation service for sentence-transformers and Ollama.
- `backend/app/rag/chunker.py` — Recursive character text chunker with token windowing and timestamp tracking.
- `backend/app/rag/retriever.py` — `TranscriptRetriever` with similarity ranking, threshold filtering, and `RetrievedChunk` data model.
- `backend/app/api/ingest.py` — `POST /api/ingest` route handler.
- `backend/scripts/download_transcripts.py` — Generator for sample Lenny's Podcast transcripts with rich metadata.
- `backend/scripts/ingest.py` — Standalone CLI ingestion script.
- `backend/tests/test_retrieval.py` — 11 automated unit and integration tests for Phase 2.
- `transcripts/elena_verna_plg.md` — Sample transcript on B2B PLG and PQLs.
- `transcripts/brian_balfour_four_fits.md` — Sample transcript on Four Fits framework.
- `transcripts/sean_ellis_experimentation.md` — Sample transcript on ICE scoring and PMF surveys.
- `transcripts/casey_winters_retention_loops.md` — Sample transcript on retention and growth loops.

---

## Files Modified

- `backend/app/models/db_models.py` — Added `embedding = Column(Vector(384).with_variant(JSON(), "sqlite"))` to `TranscriptChunk`.
- `backend/app/database.py` — Added HNSW index creation (`idx_transcript_chunks_embedding_hnsw`) in `init_db()`.
- `backend/app/main.py` — Mounted `ingest.router` under `/api`.

---

## Tests Executed

```bash
pytest -v
```

### Test Results (22/22 PASSED)

| Test File | Test Name | Result |
|---|---|---|
| `test_api.py` | `test_health_returns_200` | ✅ PASS |
| `test_api.py` | `test_health_has_database_component` | ✅ PASS |
| `test_api.py` | `test_create_session_default_title` | ✅ PASS |
| `test_api.py` | `test_create_session_custom_title` | ✅ PASS |
| `test_api.py` | `test_get_session_returns_history` | ✅ PASS |
| `test_api.py` | `test_get_session_not_found` | ✅ PASS |
| `test_api.py` | `test_list_sessions` | ✅ PASS |
| `test_api.py` | `test_chat_echoes_message` | ✅ PASS |
| `test_api.py` | `test_chat_with_invalid_session` | ✅ PASS |
| `test_api.py` | `test_chat_persists_messages` | ✅ PASS |
| `test_api.py` | `test_chat_empty_message_rejected` | ✅ PASS |
| `test_retrieval.py` | `test_embedding_dimensions` | ✅ PASS |
| `test_retrieval.py` | `test_embedding_batch` | ✅ PASS |
| `test_retrieval.py` | `test_embedding_empty_text` | ✅ PASS |
| `test_retrieval.py` | `test_chunker_basic_splitting` | ✅ PASS |
| `test_retrieval.py` | `test_chunker_timestamp_extraction` | ✅ PASS |
| `test_retrieval.py` | `test_idempotent_ingestion` | ✅ PASS |
| `test_retrieval.py` | `test_retriever_returns_relevant_chunks` | ✅ PASS |
| `test_retrieval.py` | `test_retriever_threshold_filtering` | ✅ PASS |
| `test_retrieval.py` | `test_retriever_empty_results_on_unrelated_query` | ✅ PASS |
| `test_retrieval.py` | `test_retriever_empty_archive` | ✅ PASS |
| `test_retrieval.py` | `test_ingest_api_endpoint` | ✅ PASS |

---

## Problems Encountered & Fixes

### Problem 1: PyPI Connection Timeout on Large PyTorch Wheel
**Issue:** Initial pip installation of `torch` and `sentence-transformers` suffered transient network read timeouts on Windows.  
**Fix:** Separated `pgvector` and `numpy` install, then re-ran `pip install sentence-transformers` which completed successfully with wheels cached.

---

## Remaining Limitations (Phase 2 Boundary)

- Chat endpoint (`/api/chat`) is still running in Phase 1 echo mode (Phase 3 will connect `TranscriptRetriever` with LLM prompt construction and streaming generation).
- Multi-provider LLM routing (Ollama / Anthropic / OpenAI) will be implemented in Phase 3.
- Ship 30 for 30 skill will be implemented in Phase 4.
- Artifact generation and viewer will be implemented in Phase 5.

---

## Verification Commands

```bash
# 1. Run all retrieval and API tests
cd backend
pytest -v

# 2. Run standalone transcript download script
python scripts/download_transcripts.py --output-dir ../transcripts

# 3. Ingest transcripts into database (when Docker Compose is running)
python scripts/ingest.py --transcripts-dir ../transcripts

# 4. Trigger ingestion via REST API
curl -X POST http://localhost:8000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"transcripts_dir": "transcripts"}'
```

---

## Suggested Commit Message

```
feat(phase-2): ingestion & retrieval — sentence-transformers embeddings, recursive chunker, pgvector HNSW index, idempotent ingestion pipeline, TranscriptRetriever with threshold filtering
```

