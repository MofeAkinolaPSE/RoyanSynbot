import { useState } from "react";
import { Copy, Check, FileDown } from "lucide-react";
import { Button } from "@/components/ui/button";

/** Returns true if the content looks like a structured LLM-generated report
 * (as opposed to a short conversational reply) — used to decide whether to
 * render with section/heading structure and offer a Word-doc export. */
export function isReportContent(text: string): boolean {
  return (
    text.includes("## Executive Summary") ||
    text.includes("## Key Findings") ||
    (text.includes("# ") && text.includes("## ") && text.length > 400)
  );
}

/** Renders a single inline line of text, turning **bold** markers into real
 * bold instead of showing literal asterisks — a safety net for the rare case
 * where a conversational-mode reply still slips in Markdown despite being
 * told not to. */
function InlineMarkdown({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean);
  return (
    <>
      {parts.map((part, i) =>
        part.startsWith("**") && part.endsWith("**") ? (
          <strong key={i}>{part.slice(2, -2)}</strong>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </>
  );
}

/** Plain conversational message — no headings/bullets expected, just prose
 * with an inline-bold safety net. */
export function ChatText({ content, className }: { content: string; className?: string }) {
  const lines = content.split("\n");
  return (
    <p className={className ?? "whitespace-pre-wrap text-sm leading-relaxed"}>
      {lines.map((line, i) => (
        <span key={i}>
          <InlineMarkdown text={line} />
          {i < lines.length - 1 && <br />}
        </span>
      ))}
    </p>
  );
}

/** Render report markdown as structured HTML-like JSX blocks, with copy and
 * Word (.docx) export actions. */
export function ReportRenderer({ content }: { content: string }) {
  const [copied, setCopied] = useState(false);
  const [downloading, setDownloading] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const handleDownloadDocx = async () => {
    setDownloading(true);
    try {
      const { authClient } = await import("@/lib/auth-client");
      const { apiUrl } = await import("@/lib/api-base");
      const token = await authClient.getToken();
      const res = await fetch(apiUrl("/reports/generate/docx"), {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ intent_text: content.slice(0, 200) }),
      });
      if (!res.ok) throw new Error(await res.text());
      const blob = await res.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `roy_report_${new Date().toISOString().slice(0, 10)}.docx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } catch {
      // Silent — user can copy manually if download fails
    } finally {
      setDownloading(false);
    }
  };

  const lines = content.split("\n");
  return (
    <div className="space-y-1 text-sm leading-relaxed">
      <div className="flex justify-end gap-2 mb-2">
        <Button size="sm" variant="ghost" className="h-7 gap-1.5 text-xs" onClick={handleDownloadDocx} disabled={downloading}>
          <FileDown className="h-3.5 w-3.5" />
          {downloading ? "Generating…" : "Word (.docx)"}
        </Button>
        <Button size="sm" variant="ghost" className="h-7 gap-1.5 text-xs" onClick={handleCopy}>
          {copied ? <Check className="h-3.5 w-3.5 text-green-500" /> : <Copy className="h-3.5 w-3.5" />}
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      {lines.map((line, i) => {
        if (line.startsWith("# ")) {
          return <h2 key={i} className="text-base font-bold mt-2 mb-1 text-foreground">{line.slice(2)}</h2>;
        }
        if (line.startsWith("## ")) {
          return <h3 key={i} className="text-sm font-semibold mt-3 mb-0.5 text-primary">{line.slice(3)}</h3>;
        }
        if (line.startsWith("**") && line.endsWith("**")) {
          return <p key={i} className="font-semibold">{line.slice(2, -2)}</p>;
        }
        if (/^\d+\./.test(line)) {
          return <p key={i} className="pl-3 text-sm"><InlineMarkdown text={line} /></p>;
        }
        if (line.startsWith("- ") || line.startsWith("* ")) {
          return <p key={i} className="pl-3 text-sm">• <InlineMarkdown text={line.slice(2)} /></p>;
        }
        if (line.startsWith("---")) {
          return <hr key={i} className="my-2 border-border" />;
        }
        if (line.startsWith("*") && line.endsWith("*") && !line.startsWith("**")) {
          return <p key={i} className="text-xs text-muted-foreground italic">{line.slice(1, -1)}</p>;
        }
        if (line.trim() === "") {
          return <div key={i} className="h-1" />;
        }
        return <p key={i}><InlineMarkdown text={line} /></p>;
      })}
    </div>
  );
}

/** Convenience wrapper: picks ReportRenderer or plain ChatText based on
 * content shape. Use this in any chat surface that renders a bot message. */
export function ChatMessageContent({ content }: { content: string }) {
  return isReportContent(content) ? <ReportRenderer content={content} /> : <ChatText content={content} />;
}
