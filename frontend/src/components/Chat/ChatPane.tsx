/**
 * components/Chat/ChatPane.tsx
 * ─────────────────────────────
 * Primary chat interface.
 *
 * Responsibilities:
 * - Create/restore chat sessions
 * - List past sessions in a collapsible sidebar
 * - Render message history with MessageItem
 * - Accept user input and trigger useChatStream
 * - Show ModelSelector badge (always visible)
 * - Show error states in-line (not as toast/stack trace)
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type MessageData, type ProviderName, type SessionSummary } from "@/lib/api";
import { useChatStream } from "@/hooks/useChatStream";
import MessageItem from "./MessageItem";
import ModelSelector from "./ModelSelector";

interface ChatPaneProps {
  sessionId: string | null;
  onSessionChange: (id: string) => void;
}

export default function ChatPane({ sessionId, onSessionChange }: ChatPaneProps) {
  const [messages, setMessages] = useState<MessageData[]>([]);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [provider, setProvider] = useState<ProviderName>("ollama");
  const [input, setInput] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [initError, setInitError] = useState<string | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // ── SSE stream hook ────────────────────────────────────────────────────────
  const { isStreaming, streamingContent, error: streamError, sendMessage } =
    useChatStream({
      onDone: async (messageId, sources) => {
        // Reload full session to get persisted assistant message
        if (!sessionId) return;
        try {
          const session = await api.getSession(sessionId);
          setMessages(session.messages);
        } catch {
          // Best-effort; user still sees streamed content
        }
      },
    });

  // ── Scroll to bottom when new content arrives ──────────────────────────────
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  // ── Load session list ──────────────────────────────────────────────────────
  const refreshSessions = useCallback(async () => {
    try {
      const list = await api.listSessions();
      setSessions(list);
    } catch {
      // Non-fatal — sidebar can be empty
    }
  }, []);

  useEffect(() => {
    refreshSessions();
  }, [refreshSessions]);

  // ── Load specific session ──────────────────────────────────────────────────
  const loadSession = useCallback(async (id: string) => {
    setInitError(null);
    try {
      const session = await api.getSession(id);
      setMessages(session.messages);
      onSessionChange(id);
    } catch {
      setInitError("Failed to load session. Please try again.");
    }
  }, [onSessionChange]);

  // ── Create new session ─────────────────────────────────────────────────────
  const createNewSession = useCallback(async () => {
    setInitError(null);
    try {
      const session = await api.createSession("New Session");
      setMessages([]);
      onSessionChange(session.id);
      await refreshSessions();
    } catch {
      setInitError("Failed to create session. Is the backend running?");
    }
  }, [onSessionChange, refreshSessions]);

  // ── Auto-create session on first load ─────────────────────────────────────
  useEffect(() => {
    if (!sessionId) {
      createNewSession();
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Send message ───────────────────────────────────────────────────────────
  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || !sessionId || isStreaming) return;

    setInput("");

    // Optimistically add user message
    const tempUserMsg: MessageData = {
      id: crypto.randomUUID(),
      session_id: sessionId,
      role: "user",
      content: text,
      sources: undefined,
      artifacts: [],
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMsg]);

    await sendMessage(sessionId, text, "default", provider);

    // Refresh session list to update "updated_at" ordering
    refreshSessions();
  }, [input, sessionId, isStreaming, sendMessage, provider, refreshSessions]);

  // ── Keyboard shortcut: Enter to send, Shift+Enter for newline ─────────────
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // ── Auto-resize textarea ───────────────────────────────────────────────────
  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  };

  // ── Streaming placeholder message ──────────────────────────────────────────
  const streamingMsg: MessageData | null =
    isStreaming
      ? {
          id: "streaming",
          session_id: sessionId ?? "",
          role: "assistant",
          content: streamingContent,
          artifacts: [],
          created_at: new Date().toISOString(),
        }
      : null;

  return (
    <div className="flex flex-1 overflow-hidden">
      {/* ── Session Sidebar ─────────────────────────────────────────────── */}
      <aside
        className={`
          ${sidebarOpen ? "w-64" : "w-0"} transition-all duration-200
          flex-shrink-0 overflow-hidden border-r border-slate-200 bg-white
          flex flex-col
        `}
        aria-label="Session history"
      >
        <div className="p-3 border-b border-slate-100">
          <button
            onClick={createNewSession}
            className="w-full rounded-lg bg-brand-600 px-3 py-2 text-sm font-medium text-white hover:bg-brand-700 focus:outline-none focus:ring-2 focus:ring-brand-500 transition-colors"
          >
            + New Session
          </button>
        </div>

        <div className="flex-1 overflow-y-auto custom-scrollbar p-2">
          {sessions.length === 0 && (
            <p className="text-xs text-slate-400 text-center mt-4">No sessions yet</p>
          )}
          {sessions.map((s) => (
            <button
              key={s.id}
              onClick={() => loadSession(s.id)}
              className={`
                w-full text-left rounded-lg px-3 py-2 mb-1 text-sm
                hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-brand-500
                transition-colors
                ${s.id === sessionId ? "bg-brand-50 text-brand-700 font-medium" : "text-slate-700"}
              `}
            >
              <div className="truncate">{s.title}</div>
              <div className="text-xs text-slate-400 mt-0.5">
                {new Date(s.updated_at).toLocaleDateString()}
              </div>
            </button>
          ))}
        </div>
      </aside>

      {/* ── Chat Area ───────────────────────────────────────────────────── */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top bar */}
        <div className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-2">
          <button
            onClick={() => setSidebarOpen((o) => !o)}
            aria-label={sidebarOpen ? "Close sidebar" : "Open sidebar"}
            className="rounded p-1 hover:bg-slate-100 text-slate-500 focus:outline-none focus:ring-2 focus:ring-brand-500"
          >
            {sidebarOpen ? "◀" : "▶"}
          </button>
          <ModelSelector provider={provider} onChange={setProvider} disabled={isStreaming} />
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto custom-scrollbar p-4 space-y-4">
          {/* Init error */}
          {initError && (
            <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-700">
              {initError}
            </div>
          )}

          {/* Empty state */}
          {messages.length === 0 && !isStreaming && !initError && (
            <div className="flex flex-col items-center justify-center h-full text-center py-16 text-slate-400">
              <div className="text-4xl mb-4">🎙️</div>
              <h2 className="text-lg font-semibold text-slate-600 mb-2">
                Ask about growth & product
              </h2>
              <p className="text-sm max-w-xs">
                Get citation-backed answers from 200+ hours of Lenny&apos;s Podcast.
                <span className="block mt-1 text-xs text-amber-500">(Phase 1: echo mode)</span>
              </p>
            </div>
          )}

          {/* Message history */}
          {messages.map((msg) => (
            <MessageItem key={msg.id} message={msg} />
          ))}

          {/* Streaming message */}
          {streamingMsg && (
            <MessageItem
              key="streaming"
              message={streamingMsg}
              isStreaming
              streamingContent={streamingContent}
            />
          )}

          {/* Stream error */}
          {streamError && (
            <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
              <span className="font-medium">Error: </span>
              {streamError}
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* ── Input Area ────────────────────────────────────────────────── */}
        <div className="border-t border-slate-200 bg-white p-4">
          <div className="flex items-end gap-3 rounded-xl border border-slate-300 bg-slate-50 px-4 py-3 focus-within:border-brand-500 focus-within:ring-1 focus-within:ring-brand-500 transition-all">
            <textarea
              ref={inputRef}
              value={input}
              onChange={handleInput}
              onKeyDown={handleKeyDown}
              placeholder="Ask a growth or product question…"
              rows={1}
              disabled={isStreaming || !sessionId}
              aria-label="Chat input"
              className="flex-1 resize-none bg-transparent text-sm text-slate-800 placeholder-slate-400 focus:outline-none disabled:opacity-50 leading-relaxed"
              style={{ minHeight: "24px", maxHeight: "160px" }}
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || isStreaming || !sessionId}
              aria-label="Send message"
              className="flex-shrink-0 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-40 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-brand-500 transition-colors"
            >
              {isStreaming ? (
                <span className="flex items-center gap-1.5">
                  <span className="h-1.5 w-1.5 rounded-full bg-white animate-bounce [animation-delay:0ms]" />
                  <span className="h-1.5 w-1.5 rounded-full bg-white animate-bounce [animation-delay:150ms]" />
                  <span className="h-1.5 w-1.5 rounded-full bg-white animate-bounce [animation-delay:300ms]" />
                </span>
              ) : (
                "Send"
              )}
            </button>
          </div>
          <p className="mt-1.5 text-center text-xs text-slate-400">
            Shift+Enter for newline · Enter to send
          </p>
        </div>
      </div>
    </div>
  );
}
