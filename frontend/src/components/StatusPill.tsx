"use client";

import { useEffect, useState } from "react";
import { health, type HealthResponse } from "@/lib/api";

export function StatusPill() {
  const [data, setData] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    health()
      .then((d) => active && setData(d))
      .catch((e) => active && setError(String(e)));
    return () => {
      active = false;
    };
  }, []);

  if (error) {
    return (
      <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-red-700/80">
        ● backend offline
      </span>
    );
  }
  if (!data) {
    return (
      <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted">
        ○ booting…
      </span>
    );
  }
  const ok = data.status === "ok";
  return (
    <span
      className={
        "font-mono text-[10px] uppercase tracking-[0.18em] " +
        (ok ? "text-emerald-700/80" : "text-amber-700/80")
      }
      title={`Provider: ${data.llm_provider} · Reranker: ${data.reranker_enabled ? "on" : "off"}`}
    >
      ● {data.indexed_chunks.toLocaleString()} chunks · {data.llm_provider}
    </span>
  );
}
