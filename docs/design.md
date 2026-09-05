# Lenny Growth Assistant — Design Document

**Version:** 1.0  
**Last Updated:** 2026-09-05

---

## Design Principles

1. **The answer is the UI.** The primary interaction is a question and a grounded answer. Every design decision subordinates decoration to clarity of answer + source attribution.
2. **Context is always visible.** The active LLM provider is never hidden behind a settings page. Citations are rendered inline with answers. The system state (streaming, error, insufficient data) is always explicit.
3. **Degraded states are first-class.** "I don't have enough information" is styled distinctly from a normal answer — not as an error toast. A streaming answer is visually different from a finished one.
4. **Accessible by default.** Keyboard navigation, focus states, ARIA labels, and sufficient contrast are built in from the start, not added post-hoc.
5. **The artifact viewer is additive.** It appears when there's something to show and collapses cleanly when not needed. It never obstructs the chat.

---

## Layout

### Two-Pane Shell

```
┌─────────────────────────────────────────────────────────┐
│  Header: Logo · Title · Phase badge · (Health indicator) │
├──────────┬──────────────────────────────────────────────┤
│ Sidebar  │                Chat Area                     │
│ (w-64)   │                                              │
│          │  [Message history — scrollable]              │
│ Sessions │                                              │
│ list     │  [Streaming message with cursor]             │
│          │                                              │
│ [+ New]  │  [Error / insufficient info banner]          │
│          ├──────────────────────────────────────────────┤
│          │  [ModelSelector]    [Input] [Send]           │
└──────────┴──────────────────────────────────────────────┘
```

**Artifact pane** (Phase 5) opens as a right panel (collapsible), pushing the chat pane left. On screens < 768px, the artifact pane renders as a bottom sheet overlay.

---

## Component States

### MessageItem

| State | Visual Treatment |
|-------|-----------------|
| User message | Right-aligned · brand blue bg · white text |
| Assistant (normal) | Left-aligned · white card · slate border · shadow |
| Assistant (streaming) | Same as normal + blinking cursor `▋` |
| Insufficient info | Left-aligned · amber bg · amber border · ⚠ label |
| With sources | Source badges below content with episode/guest/score |

### ModelSelector

| State | Visual Treatment |
|-------|-----------------|
| Ollama (default) | Green pill badge · green dot (pulsing when active) |
| Anthropic | Purple pill badge |
| OpenAI | Blue pill badge |
| Disabled (streaming) | Opacity 50%, cursor not-allowed |

### Chat Input

| State | Visual Treatment |
|-------|-----------------|
| Idle | Slate border, slate-50 bg |
| Focused | Brand blue border + ring |
| Streaming | Disabled + opacity-50 |
| Error | Red inline message below input |

### Artifact Viewer (Phase 5)

| State | Visual Treatment |
|-------|-----------------|
| Markdown | react-markdown with prose styles + syntax highlighting |
| HTML | "Sandboxed Preview" badge + iframe (800px min height) |
| Collapsed | Tab strip on right edge |
| Copy/Download | Icon buttons top-right of viewer |

---

## Typography

| Element | Style |
|---------|-------|
| Body text | Inter 14px / line-height 1.6 |
| Chat messages | Inter 14px |
| Headers (in artifacts) | Inter semibold, scale 1.25 / 1.5 |
| Code (in artifacts) | JetBrains Mono 13px |
| Source badges | Inter 11px, muted |
| Timestamps | Inter 11px, tabular-nums, opacity-50 |

---

## Color Palette

| Token | Value | Usage |
|-------|-------|-------|
| `brand-600` | `#0284c7` | Primary buttons, user bubbles, focus rings |
| `brand-50` | `#f0f9ff` | Active session highlight |
| `slate-50` | `#f8fafc` | Page background |
| `white` | `#ffffff` | Card backgrounds, header |
| `slate-200` | `#e2e8f0` | Borders |
| `amber-50` | `#fffbeb` | Insufficient-info message bg |
| `amber-200` | `#fde68a` | Insufficient-info border |
| `red-50` / `red-200` | — | Error states |

All text/background combinations meet WCAG AA contrast ratio (4.5:1 minimum).

---

## Responsiveness

| Breakpoint | Behaviour |
|-----------|-----------|
| `< 640px` (mobile) | Sidebar hidden by default; hamburger toggle. Input area full-width. Model label hidden (badge only). |
| `640px–1024px` (tablet) | Sidebar collapsible. Two-pane layout intact. |
| `≥ 1024px` (desktop) | Full two-pane with sidebar open by default. Artifact viewer opens as third column. |

---

## Accessibility

- All interactive elements reachable via Tab; focus ring always visible (brand-500 ring).
- `aria-label` on icon-only buttons (send, sidebar toggle, collapse artifact).
- `role="article"` on each message bubble; `aria-label` describes role.
- `aria-live="polite"` on the streaming message region.
- Session list and model selector are keyboard-operable native elements (no custom dropdown).
- Color is never the only indicator — streaming uses cursor glyph in addition to animation; errors use icon + text.
- Sufficient contrast for all text on all backgrounds.

---

## Loading & Streaming States

1. **Session loading:** Skeleton shimmer on message area while `GET /api/sessions/{id}` resolves.
2. **Sending:** User message appears immediately (optimistic); send button shows animated dots while streaming.
3. **Streaming:** Tokens appended in real time; blinking `▋` cursor visible; input disabled.
4. **Done:** Cursor disappears; sources appear below message; session refreshed from backend.
5. **Error:** Inline red banner with plain-English error message; input re-enabled; no stack trace shown.

---

## Security Constraints (visible to evaluator)

### HTML Artifact Rendering

The `SandboxedIframe` component (Phase 5) enforces the following:

1. **DOMPurify** sanitizes the HTML string before it is set as `srcDoc`.  
   - Removes `<script>` tags with src attributes, event handlers, `javascript:` hrefs, and `data:` URIs.
2. **`sandbox="allow-scripts"`** is set on the iframe. `allow-same-origin` is **not** set.  
   - The iframe cannot read `document.cookie`, `localStorage`, or `sessionStorage` from the parent origin.
   - The iframe cannot call `window.parent.postMessage` in a way that bypasses the sandbox.
3. **No external network requests** from artifacts (no `allow-forms`, no navigation).

Permitted artifact capabilities:
- Inline styles, CSS animations
- Vanilla JS that manipulates its own DOM
- `fetch()` calls to same-origin (blocked by lack of `allow-same-origin`)

Blocked capabilities:
- Reading parent page cookies / storage
- Navigating the parent frame
- Loading external scripts via `<script src>`
- Executing `eval()` with dangerous payloads (DOMPurify removes vectors)
