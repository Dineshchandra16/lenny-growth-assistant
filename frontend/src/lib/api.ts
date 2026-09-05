/**
 * lib/api.ts
 * ──────────
 * Typed API client for all backend calls.
 * All fetch calls go through this module — never call fetch() directly in components.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL
  ? `${process.env.NEXT_PUBLIC_API_URL}/api`
  : "/api";

// ─────────────────────────────────────────────────────────────────────────────
// Types (mirror backend schemas)
// ─────────────────────────────────────────────────────────────────────────────

export interface SourceCitation {
  episode_title: string;
  guest_name?: string;
  timestamp_ref?: string;
  score?: number;
}

export interface ArtifactData {
  id: string;
  artifact_type: "markdown" | "html";
  title?: string;
  content: string;
  created_at: string;
}

export interface MessageData {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  sources?: SourceCitation[];
  artifacts: ArtifactData[];
  created_at: string;
}

export interface SessionData {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: MessageData[];
}

export interface SessionSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface HealthComponent {
  status: "ok" | "degraded" | "unavailable";
  detail?: string;
}

export interface HealthData {
  status: "ok" | "degraded" | "unavailable";
  version: string;
  active_provider: string;
  components: Record<string, HealthComponent>;
}

export type ChatMode = "default" | "ship30";
export type ProviderName = "ollama" | "anthropic" | "openai";

export interface ChatRequest {
  session_id: string;
  message: string;
  mode?: ChatMode;
  provider?: ProviderName;
}

// ─────────────────────────────────────────────────────────────────────────────
// Error handling
// ─────────────────────────────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: unknown,
    message?: string
  ) {
    super(message ?? `API error ${status}`);
    this.name = "ApiError";
  }
}

async function safeFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!resp.ok) {
    let body: unknown;
    try {
      body = await resp.json();
    } catch {
      body = await resp.text();
    }
    throw new ApiError(resp.status, body, `${resp.status} ${resp.statusText}`);
  }

  return resp.json() as Promise<T>;
}

// ─────────────────────────────────────────────────────────────────────────────
// API functions
// ─────────────────────────────────────────────────────────────────────────────

export const api = {
  /** GET /api/health */
  health(): Promise<HealthData> {
    return safeFetch<HealthData>(`${API_BASE}/health`);
  },

  /** POST /api/sessions */
  createSession(title = "New Session"): Promise<SessionData> {
    return safeFetch<SessionData>(`${API_BASE}/sessions`, {
      method: "POST",
      body: JSON.stringify({ title }),
    });
  },

  /** GET /api/sessions */
  listSessions(): Promise<SessionSummary[]> {
    return safeFetch<SessionSummary[]>(`${API_BASE}/sessions`);
  },

  /** GET /api/sessions/{id} */
  getSession(sessionId: string): Promise<SessionData> {
    return safeFetch<SessionData>(`${API_BASE}/sessions/${sessionId}`);
  },

  /**
   * POST /api/chat — returns a raw Response for SSE streaming.
   * Callers must handle the ReadableStream themselves (see useChatStream).
   */
  async chatStream(req: ChatRequest): Promise<Response> {
    const resp = await fetch(`${API_BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    });

    if (!resp.ok) {
      let body: unknown;
      try {
        body = await resp.json();
      } catch {
        body = await resp.text();
      }
      throw new ApiError(resp.status, body);
    }

    return resp;
  },
};
