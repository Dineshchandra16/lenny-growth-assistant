"use client";

import DOMPurify from "dompurify";

interface SandboxedIframeProps {
  html: string;
  title?: string;
}

export default function SandboxedIframe({ html, title = "HTML artifact" }: SandboxedIframeProps) {
  const sanitizedHtml = DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
    FORBID_ATTR: ["srcdoc"],
  });

  return (
    <iframe
      title={title}
      srcDoc={sanitizedHtml}
      sandbox="allow-scripts"
      className="h-96 w-full rounded-lg border border-slate-200 bg-white"
      referrerPolicy="no-referrer"
    />
  );
}
