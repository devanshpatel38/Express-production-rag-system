"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Source, HealingEvent } from "@/lib/api";
import { HealingTrace } from "@/components/HealingTrace";

interface Props {
  content: string;
  sources?: Source[];
  latency_ms?: number;
  reranked?: boolean;
  streaming?: boolean;
  trace?: HealingEvent[];
  fromCache?: boolean;
  fallback?: boolean;
  attempts?: number;
  // Human-readable label of the pipeline stage currently running (live).
  liveStage?: string;
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
  trace,
  fromCache,
  fallback,
  attempts,
  liveStage,
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
            <span className="role">{liveStage ? "healing" : "retrieving"}</span>
            <span>·</span>
            <span className="latency">{liveStage ?? "querying index…"}</span>
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
            {fallback && (
              <>
                <span>·</span>
                <span className="fallback-tag">low confidence</span>
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

      {trace && trace.length > 0 && (
        <HealingTrace
          trace={trace}
          fromCache={fromCache}
          fallback={fallback}
          attempts={attempts}
          live={streaming}
        />
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