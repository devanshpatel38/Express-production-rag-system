"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Source } from "@/lib/api";

interface Props {
  content: string;
  sources?: Source[];
  latency_ms?: number;
  reranked?: boolean;
  streaming?: boolean;
  isPanelOpen?: boolean;
  onOpenSources?: () => void;
}

function ChevIcon() {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
      <path d="M2.5 3.5L5 6L7.5 3.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function MessageBubble({
  content,
  sources,
  latency_ms,
  reranked,
  streaming,
  isPanelOpen,
  onOpenSources,
}: Props) {
  // Pre-first-token phase: no answer text yet, pipeline still working.
  const thinking = streaming && !content;

  return (
    <div className="msg msg-assistant msg-animate">
      <div className="assistant-head">
        {thinking ? (
          <>
            <span className="role">retrieving</span>
            <span>·</span>
            <span className="latency">searching the report…</span>
          </>
        ) : (
          <>
            <span className="role">assistant</span>
            {latency_ms !== undefined && (
              <>
                <span>·</span>
                <span className="latency">
                  <strong>{latency_ms}ms</strong>
                  {sources && <> · {sources.length} chunks</>}
                </span>
              </>
            )}
            {reranked && (
              <>
                <span>·</span>
                <span className="reranked">reranked</span>
              </>
            )}
          </>
        )}
      </div>

      {thinking ? (
        <div className="assistant-body">
          <p style={{ color: "var(--text-3)" }}>
            <span className="dots">
              <span />
              <span />
              <span />
            </span>
          </p>
        </div>
      ) : (
        <div className="assistant-body">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
          {streaming && <span className="stream-cursor">▍</span>}
        </div>
      )}

      {!streaming && sources && sources.length > 0 && (
        <button
          className={"sources-trigger" + (isPanelOpen ? " is-active" : "")}
          onClick={onOpenSources}
        >
          <span className="count">{sources.length}</span>
          sources
          <ChevIcon />
        </button>
      )}
    </div>
  );
}
