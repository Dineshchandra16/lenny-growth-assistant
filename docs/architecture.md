# Lenny Growth Assistant — Architecture Document

**Version:** 1.0  
**Last Updated:** 2026-09-05

---

## System Overview

The Lenny Growth Assistant is a full-stack RAG (Retrieval-Augmented Generation) application. It ingests podcast transcripts into a vector database, retrieves relevant chunks on each user query, and generates grounded answers via a configurable LLM provider.

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER BROWSER                              │
│   Next.js (App Router) · Tailwind · TypeScript                  │
│   ChatPane → useChatStream → SSE → /api/chat                    │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTP / SSE
┌────────────────────────▼────────────────────────────────────────┐
│                    FastAPI (uvicorn ASGI)                         │
│                                                                   │
│  /api/health    /api/sessions    /api/chat    /api/artifacts     │
│       │               │              │               │           │
│  [health.py]   [sessions.py]    [chat.py]     (Phase 5)         │
│                         └────────────┘                           │
│                              │ services (never direct DB)        │
│           ┌──────────────────┼─────────────────────┐            │
│           ▼                  ▼                      ▼            │
│      [retriever.py]   [BaseLLMProvider]      [artifact_gen]      │
│      [embeddings.py]       │                  (Phase 5)         │
│           │          ┌─────┴──────┐                             │
│           │     [OllamaProvider] [AnthropicProvider/            │
│           │          │            OpenAIProvider]               │
│           ▼          ▼                                           │
│      pgvector    HTTP calls                                      │
│      HNSW idx    (external)                                      │
└──────────┬──────────────────────────────────────────────────────┘
           │
┌──────────▼──────────────────────────────────────────────────────┐
│            PostgreSQL 16 + pgvector                               │
│                                                                   │
│  sessions  messages  artifacts  transcript_chunks                │
│                                 (HNSW on embedding vector)       │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Schema

### sessions
| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | auto-generated |
| title | VARCHAR(255) | user-visible name |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | bumped on each message |

### messages
| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| session_id | UUID FK → sessions | CASCADE delete |
| role | VARCHAR(20) | "user" \| "assistant" |
| content | TEXT | full message text |
| sources | JSONB | `[{episode_title, guest_name, timestamp_ref, score}]` |
| created_at | TIMESTAMPTZ | ordered within session |

### artifacts
| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| message_id | UUID FK → messages | CASCADE delete |
| artifact_type | VARCHAR(20) | "markdown" \| "html" |
| title | VARCHAR(255) | |
| content | TEXT | raw markdown or html |
| created_at | TIMESTAMPTZ | |

### transcript_chunks
| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| episode_title | VARCHAR(512) | |
| guest_name | VARCHAR(255) | nullable |
| publish_date | VARCHAR(50) | ISO date string |
| timestamp_ref | VARCHAR(100) | "HH:MM:SS" reference |
| chunk_text | TEXT | raw chunk content |
| token_count | INTEGER | approximate token count |
| embedding | vector(384) | all-MiniLM-L6-v2 output; added Phase 2 |
| created_at | TIMESTAMPTZ | |

**Index:** `CREATE INDEX ON transcript_chunks USING hnsw (embedding vector_cosine_ops)` (Phase 2)

---

## API Endpoints

### GET /api/health
Returns structured status of all components. Never 500s — component failures are reported in payload.

```json
{
  "status": "ok|degraded|unavailable",
  "version": "1.0.0",
  "active_provider": "ollama",
  "components": {
    "database": {"status": "ok"},
    "ollama": {"status": "ok"},
    "vector_index": {"status": "degraded", "detail": "0 chunks — run ingestion"}
  }
}
```

### POST /api/sessions
Body: `{"title": "string (optional)"}`  
Returns: Full `SessionResponse` with `messages: []`

### GET /api/sessions
Returns: `SessionSummary[]` ordered by `updated_at DESC`

### GET /api/sessions/{session_id}
Returns: Full `SessionResponse` with ordered message history including sources and artifacts.  
404 if session not found.

### POST /api/chat
Body:
```json
{
  "session_id": "uuid",
  "message": "string",
  "mode": "default|ship30",
  "provider": "ollama|anthropic|openai|null"
}
```
Response: `text/event-stream` SSE  
```
data: {"type": "chunk", "content": "token", "done": false}
data: {"type": "done", "message_id": "uuid", "sources": [...]}
```
Errors: 404 (session not found), 422 (validation), 503 (provider unavailable)

### POST /api/ingest (Phase 2)
Triggers transcript ingestion pipeline. Reports `{added, updated, skipped}` counts.

### GET /api/artifacts/{artifact_id} (Phase 5)
Returns persisted artifact by ID.

---

## Component Boundaries

### Rule: Layers never bypass each other
- Route handlers (`app/api/`) → call service functions only; never access DB or LLM directly
- Service functions → call `BaseLLMProvider` for LLM; call `retriever.py` for RAG
- `BaseLLMProvider` → the only layer that knows about Ollama / Anthropic / OpenAI
- `retriever.py` → the only layer that performs pgvector queries

### app/api/ — Route Handlers
Thin. Parse request → validate → call service → return schema. No business logic.

### app/rag/ — Retrieval Layer
- `embeddings.py`: generate query + chunk embeddings (sentence-transformers or Ollama)
- `retriever.py`: pgvector cosine similarity search with threshold filtering

### app/providers/ — LLM Provider Layer
- `base.py`: `BaseLLMProvider` abstract class with `async_chat()` and `stream_chat()` methods
- `ollama_provider.py`: calls `http://ollama:11434/api/chat`
- `cloud_provider.py`: wraps Anthropic SDK or OpenAI SDK

### app/skills/ — Structured Skills
- `ship30_writer.py`: prompt construction + word-count/structure validation for essay skill
- `artifact_generator.py`: detect and parse `<artifact>` tags from model output

---

## Ingestion & Retrieval Flow

```
Transcripts (*.md / *.txt)
         │
         ▼
download_transcripts.py → transcripts/ directory
         │
         ▼
ingest.py
  ├─ Parse metadata (title, guest, date, timestamps)
  ├─ Recursive character split (600 tokens, 100 overlap)
  ├─ Embed each chunk (sentence-transformers or Ollama)
  ├─ Upsert into transcript_chunks (idempotent by episode+chunk_index)
  └─ Build HNSW index on embedding column
         │
         ▼
On user query:
  1. Embed query → 384-dim vector
  2. pgvector cosine search → top K chunks (K=5, threshold=0.30)
  3. If 0 chunks above threshold → "insufficient information" response
  4. Build grounded system prompt with chunks + citation format
  5. Stream answer via active LLM provider
  6. Persist message + sources JSONB
```

---

## Provider Routing

```
ChatRequest.provider field
        │
        ▼ (or DEFAULT_LLM_PROVIDER env var if None)
  ┌─────┴──────────────────────┐
  │  get_provider(name) factory│
  └─────┬────────┬─────────────┘
        │        │
  OllamaProvider  AnthropicProvider / OpenAIProvider
        │                  │
  http://ollama:11434  SDK client
        │                  │
  BaseLLMProvider.stream_chat() → AsyncGenerator[str, None]
```

If provider is unavailable (Ollama not running, key missing/invalid):
- Raise `ProviderUnavailableError` → caught in route → 503 response with structured message

---

## Security

| Control | Implementation |
|---------|---------------|
| HTML artifact XSS | DOMPurify sanitization + `sandbox="allow-scripts"` iframe (no `allow-same-origin`) |
| Request validation | pydantic v2 on every endpoint |
| Session trust | Session UUID looked up in DB — never trusted from client alone |
| Secret management | All keys via env vars only; `.env` in `.gitignore` |
| Log safety | API keys and provider payloads never logged |
| Error responses | Structured `ErrorDetail` only; no raw tracebacks to client |
| CORS | Restricted to `FRONTEND_ORIGIN` env var |

---

## Deployment Topology

```
docker-compose
  ├─ db        → pgvector/pgvector:pg16  (port 5432)
  ├─ backend   → python:3.11-slim / uvicorn (port 8000)
  ├─ frontend  → node:20-alpine / Next.js (port 3000)
  └─ ollama*   → ollama/ollama:latest (port 11434)  *profile: ollama
```

Backend proxied via Next.js rewrites: `frontend:3000/api/*` → `backend:8000/api/*`

All services communicate on the default Docker bridge network. Only ports 3000 (frontend) needs external exposure for end-users; 8000 (API docs) and 5432 (DB) should be firewalled in production.
