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
  if (streaming) {
    return (
      <div className="msg msg-assistant msg-animate">
        <div className="assistant-head">
          <span className="role">retrieving</span>
          <span>·</span>
          <span className="latency">querying index…</span>
        </div>
        <div className="assistant-body">
          <p style={{ color: "var(--text-3)" }}>
            <span className="dots">
              <span />
              <span />
              <span />
            </span>
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="msg msg-assistant msg-animate">
      <div className="assistant-head">
        <span className="role">assistant</span>
        <span>·</span>
        {latency_ms !== undefined && (
          <span className="latency">
            <strong>{latency_ms}ms</strong>
            {sources && <> · {sources.length} chunks</>}
          </span>
        )}
        {reranked && (
          <>
            <span>·</span>
            <span className="reranked">reranked</span>
          </>
        )}
      </div>

      <div className="assistant-body">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
      </div>

      {sources && sources.length > 0 && (
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