"use client";

import { useState } from "react";
import ChatPane from "@/components/Chat/ChatPane";

export default function HomePage() {
  const [sessionId, setSessionId] = useState<string | null>(null);

  return (
    <div className="flex h-full flex-col">
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-3 shadow-sm">
        <div className="flex items-center gap-3">
          {/* Logo mark */}
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-white text-sm font-bold">
            L
          </div>
          <div>
            <h1 className="text-base font-semibold text-slate-900 leading-tight">
              Lenny Growth Assistant
            </h1>
            <p className="text-xs text-slate-500">
              Grounded insights from Lenny&apos;s Podcast
            </p>
          </div>
        </div>

        {/* Phase 1: simple badge */}
        <div className="flex items-center gap-2 rounded-full border border-slate-200 bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
          <span className="h-2 w-2 rounded-full bg-amber-400 animate-pulse" />
          Phase 1 — Echo Mode
        </div>
      </header>

      {/* ── Main layout ─────────────────────────────────────────────────── */}
      <main className="flex flex-1 overflow-hidden">
        {/* Chat pane takes full width in Phase 1 */}
        <ChatPane sessionId={sessionId} onSessionChange={setSessionId} />
      </main>
    </div>
  );
}
