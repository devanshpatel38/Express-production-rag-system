"use client";

import { useState } from "react";
import type { HealingEvent, HealingStage } from "@/lib/api";

// One short label per stage for the timeline. Terse so the trace stays
// scannable even on 8+ events.
const STAGE_LABEL: Record<HealingStage, string> = {
  routing: "route",
  cache_hit: "cache",
  hyde: "hyde",
  retrieval: "retrieve",
  grading: "grade",
  rerank: "rerank",
  rewrite: "rewrite",
  generation: "generate",
  faithfulness: "verify",
  retry: "retry",
  give_up: "give up",
  done: "done",
};

// Stages that represent the system *correcting itself* get the accent colour
// so they pop visually — that's the whole point of surfacing the trace.
const HEALING_STAGES = new Set<HealingStage>([
  "rewrite",
  "retry",
  "give_up",
  "hyde",
  "cache_hit",
]);

interface Props {
  trace: HealingEvent[];
  fromCache?: boolean;
  fallback?: boolean;
  attempts?: number;
  // When true the trace is rendered open and un-collapsible (live, in-flight).
  live?: boolean;
}

function ChevIcon() {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
      <path
        d="M2.5 3.5L5 6L7.5 3.5"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function HealingTrace({ trace, fromCache, fallback, attempts, live }: Props) {
  const [open, setOpen] = useState(false);
  if (!trace || trace.length === 0) return null;

  const expanded = live || open;

  return (
    <div className={"ht" + (live ? " ht-live" : "")}>
      <button
        type="button"
        className="ht-summary"
        onClick={() => !live && setOpen((v) => !v)}
        aria-expanded={expanded}
      >
        {!live && (
          <span className={"ht-chev" + (expanded ? " is-open" : "")}>
            <ChevIcon />
          </span>
        )}
        <span className="ht-summary-label">
          Self-healing trace · {trace.length} step{trace.length === 1 ? "" : "s"}
        </span>
        {attempts !== undefined && attempts > 1 && (
          <span className="ht-badge ht-badge-attempts">{attempts} attempts</span>
        )}
        {fromCache && <span className="ht-badge ht-badge-cache">cached</span>}
        {fallback && <span className="ht-badge ht-badge-fallback">fallback</span>}
      </button>

      {expanded && (
        <ol className="ht-list">
          {trace.map((ev, i) => {
            const isHealing = HEALING_STAGES.has(ev.stage);
            const to = ev.detail && (ev.detail as any).to;
            return (
              <li key={i} className="ht-step">
                <span className="ht-step-dot" data-healing={isHealing} />
                <span
                  className={"ht-stage" + (isHealing ? " is-healing" : "")}
                  title={`stage: ${ev.stage}`}
                >
                  {STAGE_LABEL[ev.stage] ?? ev.stage}
                </span>
                <span className="ht-attempt">#{ev.attempt}</span>
                <span className="ht-msg">{ev.message}</span>
                {typeof ev.score === "number" && (
                  <span className="ht-score">{ev.score.toFixed(2)}</span>
                )}
                {ev.stage === "rewrite" && to && (
                  <span className="ht-rewrite">
                    → <span>{String(to)}</span>
                  </span>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}