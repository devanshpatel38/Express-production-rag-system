"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Source } from "@/lib/api";

interface Props {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  latency_ms?: number;
}

export function MessageBubble({ role, content, sources, latency_ms }: Props) {
  const isUser = role === "user";

  return (
    <article className="animate-fade-up">
      <header className="flex items-baseline gap-3 mb-2">
        <span
          className={
            "font-serif text-sm tracking-wide " + (isUser ? "text-muted" : "text-ink")
          }
        >
          {isUser ? "You" : "Express Docs"}
        </span>
        <span className="h-px flex-1 bg-rule" aria-hidden />
        {latency_ms !== undefined && (
          <span className="text-[11px] font-mono text-muted">{latency_ms} ms</span>
        )}
      </header>

      <div
        className={
          "prose-answer text-[15px] " +
          (isUser ? "text-ink/85" : "text-ink")
        }
      >
        {isUser ? (
          <p>{content}</p>
        ) : (
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
        )}
      </div>

      {sources && sources.length > 0 && (
        <details className="mt-4 group">
          <summary className="cursor-pointer font-mono text-[11px] uppercase tracking-[0.15em] text-muted hover:text-ink">
            Sources · {sources.length}
          </summary>
          <ol className="mt-3 space-y-2">
            {sources.map((s, i) => (
              <li key={s.chunk_id} className="border-l-2 border-accent/60 pl-3">
                <div className="flex items-baseline gap-2 text-[11px] font-mono text-muted">
                  <span className="text-accent font-bold">[#{i + 1}]</span>
                  <span>{s.source_path}</span>
                  <span className="ml-auto">score {s.score.toFixed(3)}</span>
                </div>
                <div className="text-[12.5px] text-ink/75 mt-1 italic font-serif">
                  {s.title} — {s.snippet}
                </div>
              </li>
            ))}
          </ol>
        </details>
      )}
    </article>
  );
}
