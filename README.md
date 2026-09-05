# Lenny Growth Assistant

> AI-powered Q&A over *Lenny's Podcast* — citation-backed product and growth insights for PMs and growth leaders.

---

## Quick Start

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Docker Engine + Compose v24+)
- For local LLM: [Ollama](https://ollama.ai/) installed and running with `llama3.2:3b` pulled

### 1. Clone & Configure

```bash
git clone <repo-url> lenny-growth-assistant
cd lenny-growth-assistant
cp .env.example .env
# Edit .env — add your ANTHROPIC_API_KEY or OPENAI_API_KEY if using cloud
```

### 2. Start the Stack

```bash
# Local (Ollama must be running separately — see note below)
docker-compose up

# With Ollama inside Docker (pulls model on first run, takes a few minutes)
docker-compose --profile ollama up
```

> **Note on Ollama:** If running Ollama natively on your Mac/Windows host (recommended for GPU access), set `OLLAMA_BASE_URL=http://host.docker.internal:11434` in your `.env`. If running Ollama inside Docker, use the `--profile ollama` flag above.

Services start on:
| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs | http://localhost:8000/api/docs |
| Database | localhost:5432 |

### 3. Run Transcript Ingestion (Phase 2+)

```bash
# Place your transcript .md or .txt files in transcripts/
# Then run ingestion inside the backend container:
docker-compose exec backend python scripts/ingest.py --transcripts-dir /app/transcripts
```

---

## Environment Variables

See [`.env.example`](.env.example) for all variables with descriptions.

Key settings:
| Variable | Default | Description |
|----------|---------|-------------|
| `DEFAULT_LLM_PROVIDER` | `ollama` | Active LLM: `ollama`, `anthropic`, `openai` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API endpoint |
| `OLLAMA_MODEL` | `llama3.2:3b` | Local model name |
| `ANTHROPIC_API_KEY` | *(unset)* | Required for Anthropic Claude |
| `OPENAI_API_KEY` | *(unset)* | Required for OpenAI GPT-4o |
| `POSTGRES_PASSWORD` | `lenny_secret` | **Change for production** |

Switching providers requires **no code changes** — set `DEFAULT_LLM_PROVIDER` and restart.

---

## Running Tests

```bash
# Install test dependencies locally
cd backend
pip install -r requirements.txt
pip install aiosqlite pytest-asyncio httpx

# Run all tests
pytest -v

# Run specific test file
pytest tests/test_api.py -v
```

---

## Health Check

```bash
curl http://localhost:8000/api/health | python -m json.tool
```

Expected response:
```json
{
  "status": "degraded",
  "active_provider": "ollama",
  "components": {
    "database": {"status": "ok"},
    "ollama": {"status": "ok"},
    "vector_index": {"status": "degraded", "detail": "0 chunks — run ingestion"}
  }
}
```

*`degraded` is expected until transcripts are ingested in Phase 2.*

---

## Project Structure

```
lenny-growth-assistant/
├── .env.example            ← Environment template
├── docker-compose.yml      ← Single-command deployment
├── README.md
├── docs/
│   ├── PRD.md              ← Discovery brief, metrics, scope
│   ├── architecture.md     ← Schema, endpoints, component boundaries
│   └── design.md           ← UI/UX, accessibility, security constraints
├── agent_transcripts/      ← Coding-agent phase logs
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── pyproject.toml      ← pytest config
│   ├── scripts/
│   │   ├── download_transcripts.py
│   │   └── ingest.py
│   ├── app/
│   │   ├── main.py         ← FastAPI app, CORS, lifespan
│   │   ├── config.py       ← Pydantic-settings configuration
│   │   ├── database.py     ← Async SQLAlchemy engine
│   │   ├── models/
│   │   │   ├── db_models.py    ← ORM models
│   │   │   └── schemas.py      ← Pydantic v2 contracts
│   │   ├── api/
│   │   │   ├── health.py       ← GET /api/health
│   │   │   ├── sessions.py     ← Session CRUD
│   │   │   └── chat.py         ← POST /api/chat (SSE)
│   │   ├── providers/      ← Phase 3: LLM routing
│   │   ├── rag/            ← Phase 2: Retrieval
│   │   └── skills/         ← Phase 4–5: Skills
│   └── tests/
│       └── test_api.py
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── next.config.js
    ├── tailwind.config.js
    └── src/
        ├── app/
        │   ├── layout.tsx
        │   ├── page.tsx
        │   └── globals.css
        ├── components/
        │   ├── Chat/
        │   │   ├── ChatPane.tsx
        │   │   ├── MessageItem.tsx
        │   │   └── ModelSelector.tsx
        │   └── Artifact/
        │       ├── ArtifactViewer.tsx  ← Phase 5
        │       └── SandboxedIframe.tsx ← Phase 5
        ├── hooks/
        │   └── useChatStream.ts
        └── lib/
            └── api.ts
```

---

## Troubleshooting

### Backend won't start
```bash
# Check logs
docker-compose logs backend

# Common: DB not ready
docker-compose restart backend
```

### Ollama provider shows "unavailable" in health check
- Ensure Ollama is running: `ollama list`
- Check `OLLAMA_BASE_URL` in `.env`
- Pull the model: `ollama pull llama3.2:3b`

### Frontend shows "Failed to create session"
- Backend may still be starting up. Wait 30s and refresh.
- Check: `curl http://localhost:8000/api/health`

### Tests fail with database errors
- Tests use in-memory SQLite; install `aiosqlite`: `pip install aiosqlite`

### Switching from Ollama to Claude
```bash
# In .env:
DEFAULT_LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...

docker-compose restart backend
```

---

## Development (without Docker)

```bash
# Backend
cd backend
python -m venv venv && source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
# Set env vars (or create .env in backend/)
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

---

## Phase Status

| Phase | Status | Description |
|-------|--------|-------------|
| 1 — Foundations | ✅ Complete | Docker, DB, health, sessions, chat echo, UI shell |
| 2 — Ingestion | 🔜 Next | Transcript pipeline, pgvector, embeddings |
| 3 — Providers | 🔜 | Ollama + cloud routing, grounded RAG chat |
| 4 — Ship 30 | 🔜 | Essay skill |
| 5 — Artifacts | 🔜 | Artifact viewer, sandboxed iframe |
| 6 — Hardening | 🔜 | Logging, resilience, full test suite |

---

## Demo Checklist (Phase 1)

1. `docker-compose up` — all services green
2. Open http://localhost:3000
3. Type a message → receive SSE echo response
4. Refresh page → messages persist (session resumes)
5. `curl http://localhost:8000/api/health` → structured JSON response
6. Create second session — both appear in sidebar

---

*Built by the Forward-Deployed Engineering team. See `docs/` for full PRD, architecture, and design documents.*
