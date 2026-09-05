# Lenny Growth Assistant — Product Requirements Document

**Version:** 1.0  
**Status:** Active  
**Owner:** Forward-Deployed Engineering  
**Last Updated:** 2026-09-05

---

## Discovery Brief

### User & Problem

**Primary User:** Growth Product Manager or Product Leader at a tech company who regularly references *Lenny's Podcast* as a source of product and growth strategy.

**Problem:** Lenny's Podcast has 200+ hours of audio with deep tactical insights from the world's best product and growth minds. The information is locked in audio and unstructured transcripts. There is no way to ask a specific question — e.g., *"What frameworks do successful growth teams use for experimentation?"* — and get a citation-backed answer in seconds. Listening or searching manually takes hours.

**Goal:** Let a Growth PM open a chat interface, ask any product/growth question in plain English, and receive a grounded, citation-backed answer sourced strictly from Lenny's Podcast transcript archive — or an honest "not enough information" when the archive doesn't cover the question.

---

## Success Metrics

| Metric | Target | Measurement Method |
|--------|--------|--------------------|
| Retrieval Citation Accuracy | ≥ 90% of answers include at least one correctly attributed source | Manual review of 20 questions against transcript archive |
| Local Inference Latency | < 4s to first token (Ollama, llama3.2:3b, M1 Mac or comparable) | `time curl` on `/api/chat` SSE endpoint |
| Artifact Render Safety | 0 XSS vulnerabilities in HTML artifact iframe | OWASP ZAP scan + manual test with `<script>alert(1)</script>` payload |
| Health Endpoint Uptime | `GET /api/health` responds 200 within 500ms at all times | Automated uptime check |
| Ingestion Freshness | Ingestion script runs idempotently in < 5 min for 50 episodes | `time python scripts/ingest.py` benchmark |

---

## Assumptions

1. **Transcript source:** Lenny's Podcast transcripts are available in Markdown or TXT format, either downloaded from a public source or provided manually. The system does not scrape audio or use a third-party transcription API in v1.
2. **Chunk size:** 500–800 tokens per chunk with 100-token overlap is assumed sufficient for maintaining context without exceeding LLM context windows. This is a known approximation; optimal chunk size may vary by episode format.
3. **"Cloud provider" = Anthropic:** When the spec says "cloud provider," the primary implementation targets Anthropic Claude. OpenAI is provided as a secondary option. Gemini is not in v1 scope.
4. **"Sufficient" retrieval relevance:** A cosine similarity threshold of 0.30 is the default. This is conservative — it may surface weakly relevant chunks. Operators should tune this per deployment after reviewing recall/precision tradeoffs.
5. **Local model reasoning:** `llama3.2:3b` is fast but less capable than cloud models. Complex multi-hop reasoning questions may produce lower-quality answers locally. This is an explicit trade-off, not a bug.
6. **No authentication:** v1 is a single-tenant demo system. Multi-user authentication and session isolation are explicitly out of scope.
7. **Transcript volume:** Phase 1–3 is designed for up to 200 episodes (~50k chunks). Scaling beyond this requires index parameter tuning.

---

## Scope

### Included in v1

- Single-tenant RAG chat over Lenny's Podcast transcripts
- Multi-provider LLM routing (Ollama local, Anthropic, OpenAI)
- pgvector HNSW similarity search with threshold-based fallback
- Session persistence (PostgreSQL)
- Ship 30 for 30 essay skill
- Artifact generation (Markdown + sandboxed HTML)
- Structured logging and health endpoint
- Docker Compose single-command deployment
- Full handoff documentation (PRD, architecture, design, README)

### Explicitly Excluded from v1

| Feature | Reason |
|---------|--------|
| Multi-tenant auth / user accounts | Adds significant complexity; not needed for demo |
| Billing / usage metering | Out of scope for internal tooling |
| Transcript scraping / scheduling | Manual ingestion is sufficient for v1 demo |
| Audio transcription (Whisper etc.) | Assumes pre-existing transcripts |
| Real-time Lenny feed sync | v1 is a static archive; refresh is manual |
| Mobile-native app | Responsive web is sufficient |
| Fine-tuning or custom models | Infrastructure out of scope for v1 |
| Feedback loop / RLHF | Requires user volume not available at demo stage |

---

## Risks & Trade-offs

### Hallucination Risk
**Risk:** LLM invents citations or fabricates content not in the transcript archive.  
**Mitigation:** Strict system prompt requires citation format `[Episode: Guest, Timestamp]`. Retrieval-gated generation — answer only uses retrieved chunks. Explicit "I do not have sufficient information" response when similarity falls below threshold.

### Latency Risk
**Risk:** Ollama on consumer hardware may exceed 4s to first token for larger models.  
**Mitigation:** Default model is `llama3.2:3b` (fastest). `mistral:7b` and `llama3.1:8b` are supported for better quality at higher latency. Model is configurable via env var.

### Cost Risk (Cloud)
**Risk:** Anthropic/OpenAI API costs can be significant at scale.  
**Mitigation:** Local Ollama is the default. Cloud providers require explicit opt-in via env var. No cloud calls are made unless `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` is set.

### Data Leakage Risk
**Risk:** Full transcript content sent to cloud LLM providers.  
**Mitigation:** Operators are explicitly warned in `.env.example`. Cloud provider is opt-in. Retrieval chunks (not full transcripts) are sent in the context window.

### Unsafe Artifact Rendering
**Risk:** LLM-generated HTML executed in the parent page context enables XSS.  
**Mitigation:** All HTML artifacts sanitized with `DOMPurify` before rendering. Rendered inside `<iframe sandbox="allow-scripts">` without `allow-same-origin`. Cannot access parent cookies, storage, or DOM.

### Local Model Reasoning Limits
**Risk:** `llama3.2:3b` cannot reliably follow complex citation format or produce high-quality Ship 30 essays.  
**Mitigation:** Structured prompt templates with explicit format instructions. Essay skill validates word count and structure. Operators are advised to use `llama3.1:8b` or cloud for production.

---

## Phase Acceptance Criteria

### Phase 1 — Foundations ✅
- [ ] `docker-compose up` starts all services without errors
- [ ] `GET /api/health` returns 200 with `status: "ok"` or `"degraded"` (never 500)
- [ ] `POST /api/sessions` creates a session and returns it with a UUID
- [ ] `GET /api/sessions/{id}` returns session with messages array
- [ ] Frontend loads at `http://localhost:3000`, shows chat shell
- [ ] Sending a message receives an SSE echo response
- [ ] Messages persist after page refresh (session reload)

### Phase 2 — Ingestion & Retrieval
- [ ] `ingest.py` runs idempotently on sample transcripts
- [ ] `transcript_chunks` table populated with HNSW index
- [ ] Similarity search returns ranked chunks above threshold
- [ ] Empty-result path handled and tested

### Phase 3 — Multi-Provider Routing & Grounded Chat
- [ ] Ollama provider streams grounded answers with citations
- [ ] Provider toggle (env + UI) switches providers without code changes
- [ ] "Insufficient information" fallback path verified
- [ ] Cloud provider works when API key is set

### Phase 4 — Ship 30 for 30 Skill
- [ ] Essay ~1,250 words, follows Ship 30 structure
- [ ] All claims cite retrieved chunks
- [ ] Word count / structure validated before returning

### Phase 5 — Artifact Generation & Viewer
- [ ] Markdown artifact renders via react-markdown
- [ ] HTML artifact in sandboxed iframe, DOMPurify applied
- [ ] XSS test payload blocked

### Phase 6 — Hardening & Handoff
- [ ] Structured JSON logs for every provider call
- [ ] Graceful degradation for all failure paths
- [ ] All automated tests pass
- [ ] `docker-compose up` verified clean
- [ ] README complete and tested by second reader
