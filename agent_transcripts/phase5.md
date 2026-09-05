# Phase 5 — Artifact Generation & Viewer

**Status:** Complete  
**Date:** 2026-09-05

## Implemented

- Added `<artifact type="markdown|html" title="...">...</artifact>` extraction from
  provider responses.
- Persisted extracted artifacts through the existing `Artifact` model and
  `Message.artifacts` relationship.
- Added `GET /api/artifacts/{artifact_id}` with structured 404 handling.
- Included artifact metadata in the chat completion SSE `done` event.
- Added Markdown rendering with `react-markdown` and `remark-gfm`.
- Added DOMPurify sanitization for HTML artifacts.
- Rendered HTML using `iframe srcDoc` with `sandbox="allow-scripts"` and no
  `allow-same-origin`, form, popup, or top-navigation permissions.
- Added artifact display to assistant messages and safe download controls.
- Added parser, persistence, retrieval, and API tests.

## Validation

- Targeted Phase 5/backend tests: passed after one fixture-query correction.
- Full backend suite: **40 passed**, with one existing Starlette deprecation
  warning.
- Frontend TypeScript check (`npm run type-check`): **passed**.
- Frontend production build (`npm run build`): **passed** after replacing the
  unsupported Tailwind Typography `@apply` usage with local Markdown styles in
  `globals.css`.

## Failure and Fix

The initial artifact persistence test used a query that correctly produced the
existing insufficient-information fallback, so no provider response or artifact
metadata was emitted. The test was corrected to use the seeded PQL transcript
query; no production behavior was changed for this fix.

The initial frontend production build failed because `globals.css` used
Tailwind Typography classes without the Typography plugin being installed. The
Phase 5 Markdown styles were rewritten using local CSS selectors, after which
the TypeScript check and production build both passed.

## Scope Boundary

Phase 6 hardening, deployment/demo work, and broad documentation overhaul were
not implemented.
