/**
 * components/Chat/MessageItem.tsx
 * ─────────────────────────────────
 * Renders a single chat message bubble.
 *
 * - User messages: right-aligned, brand-colored
 * - Assistant messages: left-aligned, white card with sources
 * - Streaming state: shows blinking cursor while tokens arrive
 * - "Insufficient information" responses rendered distinctly (not as an error)
 */

"use client";

import { type MessageData, type SourceCitation } from "@/lib/api";
import ArtifactViewer from "../Artifact/ArtifactViewer";

interface MessageItemProps {
  message: MessageData;
  isStreaming?: boolean;
  streamingContent?: string;
}

function SourceBadge({ source }: { source: SourceCitation }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 text-xs text-slate-600 border border-slate-200">
      <span className="font-medium">{source.guest_name ?? "Unknown"}</span>
      {source.timestamp_ref && (
        <span className="text-slate-400">· {source.timestamp_ref}</span>
      )}
      {source.score !== undefined && (
        <span className="text-slate-400 tabular-nums">
          {(source.score * 100).toFixed(0)}%
        </span>
      )}
    </span>
  );
}

export default function MessageItem({
  message,
  isStreaming = false,
  streamingContent = "",
}: MessageItemProps) {
  const isUser = message.role === "user";
  const displayContent = isStreaming ? streamingContent : message.content;

  const isInsufficient =
    !isUser &&
    displayContent.toLowerCase().includes("do not have sufficient information");

  return (
    <div
      className={`flex ${isUser ? "justify-end" : "justify-start"} gap-3`}
      role="article"
      aria-label={`${message.role} message`}
    >
      {/* Avatar — assistant only */}
      {!isUser && (
        <div className="flex-shrink-0 mt-1">
          <div className="h-7 w-7 rounded-full bg-brand-600 flex items-center justify-center text-white text-xs font-bold">
            L
          </div>
        </div>
      )}

      <div
        className={`
          max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed
          ${isUser
            ? "bg-brand-600 text-white rounded-tr-sm"
            : isInsufficient
            ? "bg-amber-50 border border-amber-200 text-amber-900 rounded-tl-sm"
            : "bg-white border border-slate-200 text-slate-800 rounded-tl-sm shadow-sm"
          }
        `}
      >
        {/* Insufficient-info indicator */}
        {isInsufficient && (
          <div className="flex items-center gap-1.5 mb-2 text-xs font-medium text-amber-700">
            <span>⚠</span>
            <span>Insufficient information in archive</span>
          </div>
        )}

        {/* Message content */}
        <p className={`whitespace-pre-wrap break-words ${isStreaming ? "streaming-cursor" : ""}`}>
          {displayContent || (isStreaming ? "" : "…")}
        </p>

        {/* Sources */}
        {!isUser && message.sources && message.sources.length > 0 && (
          <div className="mt-3 pt-2 border-t border-slate-100">
            <p className="text-xs text-slate-400 mb-1.5">Sources</p>
            <div className="flex flex-wrap gap-1.5">
              {message.sources.map((src, i) => (
                <SourceBadge key={i} source={src} />
              ))}
            </div>
          </div>
        )}

        {!isUser && message.artifacts?.map((artifact) => (
          <ArtifactViewer key={artifact.id} artifact={artifact} />
        ))}

        {/* Timestamp */}
        <p className={`mt-1.5 text-right text-xs opacity-50 tabular-nums`}>
          {new Date(message.created_at).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </p>
      </div>

      {/* Avatar — user only */}
      {isUser && (
        <div className="flex-shrink-0 mt-1">
          <div className="h-7 w-7 rounded-full bg-slate-300 flex items-center justify-center text-slate-700 text-xs font-bold">
            U
          </div>
        </div>
      )}
    </div>
  );
}
