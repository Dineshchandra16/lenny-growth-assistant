/**
 * hooks/useChatStream.ts
 * ──────────────────────
 * Custom hook that manages the SSE streaming lifecycle for chat.
 *
 * Features:
 * - Sends a POST /api/chat and reads the SSE stream
 * - Accumulates tokens into a streaming message
 * - Emits onChunk, onDone callbacks
 * - Handles errors gracefully (sets error state, never throws uncaught)
 * - Supports abort via AbortController
 */

"use client";

import { useCallback, useRef, useState } from "react";
import { api, ApiError, type ChatMode, type ProviderName, type SourceCitation } from "@/lib/api";

export interface StreamState {
  isStreaming: boolean;
  streamingContent: string;
  error: string | null;
}

export interface UseChatStreamOptions {
  onChunk?: (token: string, accumulated: string) => void;
  onDone?: (messageId: string, sources: SourceCitation[]) => void;
  onError?: (error: string) => void;
}

export function useChatStream(options: UseChatStreamOptions = {}) {
  const [state, setState] = useState<StreamState>({
    isStreaming: false,
    streamingContent: "",
    error: null,
  });

  const abortRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(
    async (
      sessionId: string,
      message: string,
      mode: ChatMode = "default",
      provider?: ProviderName
    ) => {
      // Cancel any in-flight stream
      abortRef.current?.abort();
      abortRef.current = new AbortController();

      setState({ isStreaming: true, streamingContent: "", error: null });

      try {
        const resp = await api.chatStream({ session_id: sessionId, message, mode, provider });

        if (!resp.body) {
          throw new Error("Response body is null — SSE not supported");
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let accumulated = "";
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          // Process complete SSE lines
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? ""; // keep incomplete last line

          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed.startsWith("data: ")) continue;

            const jsonStr = trimmed.slice("data: ".length);
            try {
              const event = JSON.parse(jsonStr) as {
                type: "chunk" | "done";
                content?: string;
                done?: boolean;
                message_id?: string;
                sources?: SourceCitation[];
              };

              if (event.type === "chunk" && event.content) {
                accumulated += event.content;
                setState((prev) => ({
                  ...prev,
                  streamingContent: accumulated,
                }));
                options.onChunk?.(event.content, accumulated);
              } else if (event.type === "done") {
                options.onDone?.(
                  event.message_id ?? "",
                  event.sources ?? []
                );
              }
            } catch {
              // Malformed SSE line — skip
            }
          }
        }

        setState({ isStreaming: false, streamingContent: "", error: null });
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") {
          setState({ isStreaming: false, streamingContent: "", error: null });
          return;
        }

        let errorMessage = "An unexpected error occurred";
        if (err instanceof ApiError) {
          const body = err.body as { detail?: { message?: string } | string };
          if (typeof body?.detail === "object" && body.detail?.message) {
            errorMessage = body.detail.message;
          } else if (typeof body?.detail === "string") {
            errorMessage = body.detail;
          } else {
            errorMessage = err.message;
          }
        } else if (err instanceof Error) {
          errorMessage = err.message;
        }

        setState({ isStreaming: false, streamingContent: "", error: errorMessage });
        options.onError?.(errorMessage);
      }
    },
    [options]
  );

  const abort = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return { ...state, sendMessage, abort };
}
