"use client";

import type { Source } from "@/lib/api";

interface Props {
  open: boolean;
  onClose: () => void;
  sources?: Source[];
  question?: string;
  latency_ms?: number;
  reranked?: boolean;
}

function XIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
      <path d="M3 3L9 9M9 3L3 9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

export function SourcesPanel({ open, onClose, sources, question, latency_ms, reranked }: Props) {
  return (
    <>
      <div className={"scrim" + (open ? " is-open" : "")} onClick={onClose} />
      <aside className={"side-panel" + (open ? " is-open" : "")} aria-hidden={!open}>
        <div className="panel-head">
          <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0, flex: 1 }}>
            <span className="panel-head-eyebrow">Retrieved sources</span>
            {question && <span className="panel-head-q">{question}</span>}
          </div>
          <button className="panel-close" onClick={onClose} title="Close (Esc)">
            <XIcon />
          </button>
        </div>

        {sources && (
          <div className="panel-meta">
            <span>
              <strong>{sources.length}</strong> chunks
            </span>
            {latency_ms !== undefined && (
              <>
                <span className="dot" />
                <span>
                  answered in <strong>{latency_ms}ms</strong>
                </span>
              </>
            )}
            <span className="dot" />
            <span>
              reranked:{" "}
              <strong style={{ color: reranked ? "var(--accent)" : "var(--text-2)" }}>
                {reranked ? "yes" : "no"}
              </strong>
            </span>
          </div>
        )}

        <div className="panel-body">
          {sources?.map((s, i) => (
            <div key={s.chunk_id} className="source-item">
              <div className="source-head">
                <div className="source-rank-row">
                  <span className={`source-rank rk-${Math.min(i + 1, 5)}`}>{i + 1}</span>
                  <span className="source-path">{s.source_path}</span>
                </div>
                <div className="source-score">
                  <span className="num">{s.score.toFixed(2)}</span>
                  <span className="lbl">score</span>
                </div>
              </div>
              <div className="source-snippet">
                {s.title && <strong>{s.title} — </strong>}
                {s.snippet}
              </div>
            </div>
          ))}
        </div>
      </aside>
    </>
  );
}