# Phase 1 — Foundations: Agent Transcript

**Phase:** 1  
**Date:** 2026-09-05  
**Status:** Complete

---

## Objective

Implement Phase 1 per spec Section 10:
- Repo scaffolding (FastAPI + Next.js App Router)
- Docker Compose with PostgreSQL 16 + pgvector, backend, frontend, optional Ollama
- `.env.example` with all documented variables
- `app/config.py` (pydantic-settings, typed, validated)
- `app/database.py` (async SQLAlchemy, session factory, `init_db`, health-check helper)
- `app/models/db_models.py` (Session, Message, Artifact, TranscriptChunk)
- `app/models/schemas.py` (Pydantic v2 contracts for all endpoints)
- `GET /api/health` (DB + Ollama + vector-index status)
- `POST /api/sessions`, `GET /api/sessions`, `GET /api/sessions/{id}`
- `POST /api/chat` (SSE echo stub — streams message back word-by-word)
- Next.js frontend shell: ChatPane, MessageItem, ModelSelector, useChatStream hook, api.ts
- Full docs: PRD.md, architecture.md, design.md, README.md

---

## Decisions Made

### 1. DB migrations strategy
**Decision:** `SQLAlchemy create_all` on startup (no Alembic in Phase 1).  
**Rationale:** Alembic adds operational complexity (migration files, version tracking) that is premature until the schema stabilises. Phase 2 will add the `embedding` vector column; that's the right time to introduce Alembic.

### 2. Chat endpoint is an SSE echo stub
**Decision:** `POST /api/chat` streams the user message back word-by-word.  
**Rationale:** The spec says Phase 1 has "base chat UI shell with no RAG yet (echoes provider output)." The echo stub lets the full SSE framing, frontend hook, and persistence logic be implemented and tested at Phase 1, so Phase 3 only needs to replace `_echo_stream()` with the real provider call.

### 3. `TranscriptChunk.embedding` column deferred
**Decision:** `TranscriptChunk` model is created in Phase 1 without the `vector` column.  
**Rationale:** SQLite (used in tests) does not support pgvector. The `embedding` column requires pgvector and is added in Phase 2. The table skeleton is created now so FK integrity and the model import chain are verified.

### 4. Test database is SQLite in-memory
**Decision:** `pytest` uses `sqlite+aiosqlite:///:memory:`.  
**Rationale:** Allows CI and local developer testing without a running PostgreSQL instance. Phase 2 tests that require pgvector will use a containerised Postgres via a `docker-compose.test.yml`.

### 5. Frontend API calls routed via Next.js rewrites
**Decision:** `next.config.js` proxies `/api/*` to `backend:8000/api/*`.  
**Rationale:** Avoids CORS complexity in the browser and keeps the frontend's API calls origin-relative. In production, the same rewrite config keeps the Docker Compose topology clean.

---

## Files Created

### Root
- `.env.example`
- `docker-compose.yml`
- `README.md`

### docs/
- `docs/PRD.md`
- `docs/architecture.md`
- `docs/design.md`

### backend/
- `backend/Dockerfile`
- `backend/requirements.txt`
- `backend/pyproject.toml`
- `backend/app/__init__.py`
- `backend/app/main.py`
- `backend/app/config.py`
- `backend/app/database.py`
- `backend/app/models/__init__.py`
- `backend/app/models/db_models.py`
- `backend/app/models/schemas.py`
- `backend/app/api/__init__.py`
- `backend/app/api/health.py`
- `backend/app/api/sessions.py`
- `backend/app/api/chat.py`
- `backend/app/providers/__init__.py`
- `backend/app/rag/__init__.py`
- `backend/app/skills/__init__.py`
- `backend/scripts/download_transcripts.py`
- `backend/scripts/ingest.py`
- `backend/tests/__init__.py`
- `backend/tests/test_api.py`

### frontend/
- `frontend/Dockerfile`
- `frontend/package.json`
- `frontend/tsconfig.json`
- `frontend/tailwind.config.js`
- `frontend/postcss.config.js`
- `frontend/next.config.js`
- `frontend/src/app/globals.css`
- `frontend/src/app/layout.tsx`
- `frontend/src/app/page.tsx`
- `frontend/src/lib/api.ts`
- `frontend/src/hooks/useChatStream.ts`
- `frontend/src/components/Chat/ChatPane.tsx`
- `frontend/src/components/Chat/MessageItem.tsx`
- `frontend/src/components/Chat/ModelSelector.tsx`
- `frontend/src/components/Artifact/ArtifactViewer.tsx`
- `frontend/src/components/Artifact/SandboxedIframe.tsx`

---

## Files Modified
None — clean slate.

---

## Tests Executed

```
pytest backend/tests/test_api.py -v
```

### Test Results

| Test | Result |
|------|--------|
| test_health_returns_200 | ✅ PASS |
| test_health_has_database_component | ✅ PASS |
| test_create_session_default_title | ✅ PASS |
| test_create_session_custom_title | ✅ PASS |
| test_get_session_returns_history | ✅ PASS |
| test_get_session_not_found | ✅ PASS |
| test_list_sessions | ✅ PASS |
| test_chat_echoes_message | ✅ PASS |
| test_chat_with_invalid_session | ✅ PASS |
| test_chat_persists_messages | ✅ PASS |
| test_chat_empty_message_rejected | ✅ PASS |

---

## Problems Encountered & Fixes

### Problem 1: SQLite in-memory + pgvector
**Issue:** `TranscriptChunk.embedding` as a `vector` column is not supported by SQLite.  
**Fix:** Deferred the `embedding` column to Phase 2. `TranscriptChunk` table is created with all other columns; the vector column is added via `ALTER TABLE` in Phase 2 once pgvector is confirmed available.

### Problem 2: pydantic `FieldValidationInfo` import
**Issue:** `FieldValidationInfo` type hint in `config.py` `field_validator` required a string annotation.  
**Fix:** Used `"FieldValidationInfo"` as a string forward-reference in the validator signature, which works with Pydantic v2 validators without needing the import at runtime.

### Problem 3: `session.updated_at` update in streaming context
**Issue:** The streaming generator runs after the request-scoped DB session is committed and closed. Updating `session.updated_at` inside the generator requires a new session.  
**Fix:** Opened a new `AsyncSessionLocal()` context inside the SSE generator to persist the assistant reply and bump `updated_at`.

### Problem 4: SQLAlchemy PostgreSQL types in SQLite test environment
**Issue:** Using `UUID` and `JSONB` directly from `sqlalchemy.dialects.postgresql` broke SQLite in-memory test compilation.
**Fix:** Refactored `db_models.py` to use `Uuid(as_uuid=True)` and `JSON().with_variant(JSONB, "postgresql")`, allowing native PostgreSQL behavior in production while supporting generic JSON/UUID in SQLite test environments.

### Problem 5: StreamingResponse engine binding in tests
**Issue:** `AsyncSessionLocal` inside `chat.py` was hardcoded to the default PostgreSQL engine, failing during in-memory SQLite test execution.
**Fix:** Updated test fixture `override_dependency` in `tests/test_api.py` to patch `app.database.AsyncSessionLocal` with `TestSessionLocal` during test executions.

---

## Remaining Limitations (Phase 1)

- Chat is an echo stub — no real LLM calls (Phase 3)
- No RAG / embeddings / transcript ingestion (Phase 2)
- `TranscriptChunk.embedding` column missing — vector search not possible yet
- No Ship 30 skill (Phase 4)
- No Artifact rendering (Phase 5)
- Structured logging configured but not tested under load
- Alembic not set up — `create_all` used for schema management
- Frontend not tested via browser (requires `npm install`)

---

## Verification Commands

```bash
# 1. Start the stack
docker-compose up

# 2. Health check
curl http://localhost:8000/api/health | python -m json.tool

# 3. Create a session
curl -X POST http://localhost:8000/api/sessions \
  -H "Content-Type: application/json" \
  -d '{"title": "Test Session"}'

# 4. Chat (SSE echo)
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "<uuid-from-step-3>", "message": "Hello growth world"}' \
  --no-buffer

# 5. Run tests (requires: pip install aiosqlite)
cd backend && pytest tests/test_api.py -v

# 6. Frontend
open http://localhost:3000
```

---

## Suggested Commit Message

```
feat(phase-1): foundations — FastAPI + Next.js scaffold, Docker Compose, health/sessions/chat endpoints, SSE echo, DB persistence
```
