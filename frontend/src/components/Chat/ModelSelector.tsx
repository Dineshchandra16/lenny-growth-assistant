/**
 * components/Chat/ModelSelector.tsx
 * ───────────────────────────────────
 * Displays the active LLM provider and lets the user switch between them.
 * Always visible — never hidden in a settings page.
 */

"use client";

import { type ProviderName } from "@/lib/api";

interface ModelSelectorProps {
  provider: ProviderName;
  onChange: (provider: ProviderName) => void;
  disabled?: boolean;
}

const PROVIDERS: { id: ProviderName; label: string; color: string; dot: string }[] = [
  { id: "ollama", label: "Ollama (Local)", color: "bg-green-100 text-green-800 border-green-200", dot: "bg-green-500" },
  { id: "anthropic", label: "Claude", color: "bg-purple-100 text-purple-800 border-purple-200", dot: "bg-purple-500" },
  { id: "openai", label: "GPT-4o", color: "bg-blue-100 text-blue-800 border-blue-200", dot: "bg-blue-500" },
];

export default function ModelSelector({ provider, onChange, disabled }: ModelSelectorProps) {
  const active = PROVIDERS.find((p) => p.id === provider) ?? PROVIDERS[0];

  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-slate-500 hidden sm:inline">Model:</span>
      <div className="relative">
        <select
          value={provider}
          onChange={(e) => onChange(e.target.value as ProviderName)}
          disabled={disabled}
          aria-label="Select LLM provider"
          className={`
            appearance-none rounded-full border px-3 py-1 pr-7 text-xs font-medium
            cursor-pointer focus:outline-none focus:ring-2 focus:ring-brand-500
            disabled:opacity-50 disabled:cursor-not-allowed
            ${active.color}
          `}
        >
          {PROVIDERS.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
        </select>
        {/* Chevron icon */}
        <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-current opacity-60">
          ▾
        </span>
      </div>
      {/* Live indicator dot */}
      <span
        className={`h-2 w-2 rounded-full ${active.dot} ${!disabled ? "animate-pulse" : ""}`}
        aria-hidden
      />
    </div>
  );
}
