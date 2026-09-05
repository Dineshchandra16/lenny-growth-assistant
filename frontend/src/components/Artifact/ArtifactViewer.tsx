"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ArtifactData } from "@/lib/api";
import SandboxedIframe from "./SandboxedIframe";

interface ArtifactViewerProps {
  artifact: ArtifactData;
}

export default function ArtifactViewer({ artifact }: ArtifactViewerProps) {
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);

  useEffect(() => {
    const blob = new Blob([artifact.content], {
      type: artifact.artifact_type === "html" ? "text/html" : "text/markdown",
    });
    const url = URL.createObjectURL(blob);
    setDownloadUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [artifact]);

  return (
    <section className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3" aria-label="Generated artifact">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-700">
          {artifact.title ?? "Generated artifact"}
        </h3>
        <a
          href={downloadUrl ?? undefined}
          download={artifact.title ?? `artifact.${artifact.artifact_type === "html" ? "html" : "md"}`}
          className="text-xs font-medium text-brand-700 hover:underline"
        >
          Download
        </a>
      </div>
      {artifact.artifact_type === "markdown" ? (
        <div className="prose-chat">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{artifact.content}</ReactMarkdown>
        </div>
      ) : (
        <SandboxedIframe html={artifact.content} title={artifact.title ?? "HTML artifact"} />
      )}
    </section>
  );
}
