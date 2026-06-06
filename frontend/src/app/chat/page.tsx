"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import Link from "next/link";
import Image from "next/image";
import {
  chat,
  chatStream,
  health as fetchHealth,
  type ChatMessage,
  type Source,
  type HealingEvent,
  type HealthResponse,
} from "@/lib/api";
import { MessageBubble } from "@/components/MessageBubble";
import { SourcesPanel } from "@/components/SourcesPanel";

interface Turn {
  id: number;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  latency_ms?: number;
  reranked?: boolean;
  trace?: HealingEvent[];
  fromCache?: boolean;
  fallback?: boolean;
  attempts?: number;
}

const STARTER_QUESTIONS = [
  { kind: "Routing",   text: "How do I set up middleware in Express?" },
  { kind: "Errors",    text: "How does error-handling middleware work?" },
  { kind: "Static",    text: "How do I serve static files from a directory?" },
  { kind: "Lifecycle", text: "What's the difference between app.use and app.get?" },
];

// Verbose, human-readable label for the stage currently running (shown in the
// in-flight bubble head). The HealingTrace timeline uses its own terse labels.
const STAGE_LABEL: Record<string, string> = {
  routing:      "routing your question",
  cache_hit:    "cache hit — serving instantly",
  hyde:         "generating hypothetical passage",
  retrieval:    "searching documentation",
  grading:      "grading retrieved chunks",
  rerank:       "reranking results",
  rewrite:      "rewriting query for better retrieval",
  generation:   "generating answer",
  faithfulness: "verifying answer accuracy",
  retry:        "retrying with improved query",
  give_up:      "returning best-effort answer",
  done:         "finalising",
};

const GITHUB_URL = "https://github.com/devanshpatel38/Express-production-rag-system";

function ArrowIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
      <path d="M2.5 6h7M6 2.5L9.5 6 6 9.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function GithubIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38v-1.5c-2.22.48-2.69-.94-2.69-.94-.36-.92-.89-1.17-.89-1.17-.72-.49.06-.48.06-.48.8.06 1.23.83 1.23.83.72 1.23 1.88.88 2.34.67.07-.52.28-.88.51-1.08-1.77-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.83-2.15-.08-.2-.36-1.02.08-2.13 0 0 .67-.22 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.11.16 1.93.08 2.13.52.56.83 1.28.83 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48v2.2c0 .21.15.46.55.38C13.71 14.53 16 11.54 16 8c0-4.42-3.58-8-8-8z" />
    </svg>
  );
}

function SendIcon() {
  return (
    <svg viewBox="0 0 12 12" fill="none" width="12" height="12">
      <path d="M2 6L10 6M6 2L10 6L6 10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function ChatPage() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [useReranker, setUseReranker] = useState(true);
  const [useHyde, setUseHyde] = useState(false);
  const [streaming, setStreaming] = useState(true);
  const [healthData, setHealthData] = useState<HealthResponse | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const [panelTurnId, setPanelTurnId] = useState<number | null>(null);
  const [inFlightId, setInFlightId] = useState<number | null>(null);
  const threadRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const nextId = useRef(1);
  const didAutoSubmit = useRef(false);

  useEffect(() => {
    fetchHealth().then(setHealthData).catch(() => {});
  }, []);

  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight;
    }
  }, [turns, busy]);

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
  }, [input]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setPanelOpen(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const send = useCallback(async (query: string) => {
    const q = query.trim();
    if (!q || busy) return;
    setError(null);
    setInput("");

    const history: ChatMessage[] = turns.map(({ role, content }) => ({ role, content }));
    const userId = nextId.current++;
    const asstId = nextId.current++;

    setTurns((prev) => [
      ...prev,
      { id: userId, role: "user", content: q },
      { id: asstId, role: "assistant", content: "", trace: [] },
    ]);
    setBusy(true);
    setInFlightId(asstId);

    const patch = (updater: (t: Turn) => Turn) =>
      setTurns((prev) => prev.map((t) => (t.id === asstId ? updater(t) : t)));

    try {
      if (streaming) {
        const live: HealingEvent[] = [];
        const final = await chatStream(
          q,
          history,
          { useReranker, useHyde },
          {
            onEvent: (ev) => {
              live.push(ev);
              const snapshot = [...live];
              patch((t) => ({ ...t, trace: snapshot }));
            },
            onToken: (text) => {
              patch((t) => ({ ...t, content: t.content + text }));
            },
            onError: (msg) => setError(msg),
          }
        );
        patch((t) => ({
          ...t,
          content: final.answer,
          sources: final.sources,
          latency_ms: final.latency_ms,
          reranked: useReranker,
          trace: final.trace,
          fromCache: final.from_cache,
          fallback: final.fallback,
          attempts: final.attempts,
        }));
      } else {
        const resp = await chat(q, history, { useReranker, useHyde });
        patch((t) => ({
          ...t,
          content: resp.answer,
          sources: resp.sources,
          latency_ms: resp.latency_ms,
          reranked: useReranker,
          trace: resp.trace,
          fromCache: resp.from_cache,
          fallback: resp.fallback,
          attempts: resp.attempts,
        }));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setTurns((prev) => prev.filter((t) => t.id !== asstId && t.id !== userId));
    } finally {
      setBusy(false);
      setInFlightId(null);
    }
  }, [busy, turns, useReranker, useHyde, streaming]);

  // Auto-submit from ?q= URL param
  useEffect(() => {
    if (didAutoSubmit.current) return;
    const params = new URLSearchParams(window.location.search);
    const q = params.get("q");
    if (q && q.trim()) {
      didAutoSubmit.current = true;
      const t = setTimeout(() => send(q.trim()), 250);
      return () => clearTimeout(t);
    }
  }, [send]);

  const openPanel = (turnId: number) => {
    if (panelOpen && panelTurnId === turnId) {
      setPanelOpen(false);
    } else {
      setPanelTurnId(turnId);
      setPanelOpen(true);
    }
  };

  const panelTurn = turns.find((t) => t.id === panelTurnId);
  const panelQuestion = (() => {
    const idx = turns.findIndex((t) => t.id === panelTurnId);
    return idx > 0 ? turns[idx - 1].content : "";
  })();

  // Verbose label for the stage currently running on the in-flight turn.
  const liveStageFor = (t: Turn): string | undefined => {
    if (t.id !== inFlightId || !t.trace || t.trace.length === 0) return undefined;
    const last = t.trace[t.trace.length - 1];
    return STAGE_LABEL[last.stage] ?? last.stage;
  };

  return (
    <div className="app">
      {/* ─── Header ─── */}
      <header className="site-header">
        <div className="chat-brand">
          <Link href="/" className="brand-back" title="Back to home">
            ←
          </Link>
          <Link href="/" className="brand">
            <span className="brand-logo">
              <Image src="/cogito-logo-short.svg" alt="" width={24} height={13} />
            </span>
            <span>Express Docs</span>
            <span className="brand-tag">RAG</span>
          </Link>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          {healthData ? (
            <>
              <span className="header-pill hide-md">
                <span className="status-dot" />
                <span className="lbl">indexed</span>
                <span className="num">{healthData.indexed_chunks.toLocaleString()}</span>
              </span>
              {healthData.self_healing_enabled && (
                <span
                  className="header-pill heal hide-md"
                  title="Self-healing RAG: chunk grading, query rewriting, and faithfulness checks are active"
                >
                  <span className="lbl">self-healing</span>
                  <span className="num">on</span>
                </span>
              )}
              <span className="header-pill llm hide-md">
                <span className="lbl">llm</span>
                <span className="num">{healthData.llm_provider}</span>
              </span>
            </>
          ) : (
            <span className="header-pill hide-md">
              <span className="lbl">connecting…</span>
            </span>
          )}
          <a
            className="header-icon-btn"
            href={GITHUB_URL}
            target="_blank"
            rel="noopener noreferrer"
            title="View on GitHub"
          >
            <GithubIcon />
          </a>
        </div>
      </header>

      {/* ─── Main ─── */}
      <main className="main">
        <div className="thread-wrap" ref={threadRef}>
          <div className="thread">
            {turns.length === 0 && (
              <div className="hero">
                <div className="hero-eyebrow">Express.js · Official Docs</div>
                <h1>Ask anything in the Express.js documentation.</h1>
                <p>
                  Self-healing retrieval-augmented answers grounded in the official expressjs/express docs.
                  Hybrid search (dense + BM25), cross-encoder reranking, LLM chunk grading,
                  query rewriting, and faithfulness checks — with a transparent healing trace.
                </p>
                <div className="chips">
                  {STARTER_QUESTIONS.map((q) => (
                    <button key={q.text} className="chip" onClick={() => send(q.text)}>
                      <span>
                        <span className="chip-kind">{q.kind}</span>
                        {q.text}
                      </span>
                      <span className="chip-arrow" aria-hidden="true">
                        <ArrowIcon />
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {turns.map((t) =>
              t.role === "user" ? (
                <div key={t.id} className="msg msg-user msg-animate">
                  <div className="bubble-user">{t.content}</div>
                </div>
              ) : (
                <MessageBubble
                  key={t.id}
                  content={t.content}
                  sources={t.sources}
                  latency_ms={t.latency_ms}
                  reranked={t.reranked}
                  trace={t.trace}
                  fromCache={t.fromCache}
                  fallback={t.fallback}
                  attempts={t.attempts}
                  streaming={busy && t.id === inFlightId}
                  liveStage={liveStageFor(t)}
                  isPanelOpen={panelOpen && panelTurnId === t.id}
                  onOpenSources={() => openPanel(t.id)}
                />
              )
            )}

            {error && (
              <div
                style={{
                  border: "1px solid #FCA5A5",
                  background: "#FEF2F2",
                  borderRadius: 6,
                  padding: "10px 14px",
                  fontSize: 13,
                  color: "#7F1D1D",
                }}
              >
                {error}
              </div>
            )}
          </div>
        </div>

        {/* ─── Composer ─── */}
        <div className="composer-wrap">
          <form
            className="composer"
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
          >
            <textarea
              ref={textareaRef}
              className="composer-input"
              placeholder="Ask about routing, middleware, errors, request bodies…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send(input);
                }
              }}
              rows={1}
              disabled={busy}
            />
            <div className="composer-bar">
              <div className="toggle-row">
                <div className="toggle">
                  <button
                    type="button"
                    className={"switch" + (useReranker ? " on" : "")}
                    onClick={() => setUseReranker((v) => !v)}
                    aria-pressed={useReranker}
                    aria-label="Toggle reranker"
                  />
                  <label className="toggle-label" onClick={() => setUseReranker((v) => !v)}>
                    reranker
                  </label>
                </div>
                <div className="toggle">
                  <button
                    type="button"
                    className={"switch" + (useHyde ? " on" : "")}
                    onClick={() => setUseHyde((v) => !v)}
                    aria-pressed={useHyde}
                    aria-label="Toggle HyDE"
                  />
                  <label
                    className="toggle-label"
                    onClick={() => setUseHyde((v) => !v)}
                    title="Hypothetical Document Embeddings — embeds an imagined answer for better dense retrieval on vague queries."
                  >
                    hyde
                  </label>
                </div>
                <div className="toggle">
                  <button
                    type="button"
                    className={"switch" + (streaming ? " on" : "")}
                    onClick={() => setStreaming((v) => !v)}
                    aria-pressed={streaming}
                    aria-label="Toggle streaming"
                  />
                  <label
                    className="toggle-label"
                    onClick={() => setStreaming((v) => !v)}
                    title="Stream the healing steps and answer live via Server-Sent Events."
                  >
                    stream
                  </label>
                </div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span className="kbd-hint">
                  <kbd>↵</kbd> to send
                </span>
                <button
                  type="submit"
                  className="btn-ask"
                  disabled={!input.trim() || busy}
                >
                  {busy ? "thinking…" : "Ask"}
                  {!busy && <SendIcon />}
                </button>
              </div>
            </div>
          </form>
        </div>
      </main>

      {/* ─── Sources panel ─── */}
      <SourcesPanel
        open={panelOpen}
        onClose={() => setPanelOpen(false)}
        sources={panelTurn?.sources}
        question={panelQuestion}
        latency_ms={panelTurn?.latency_ms}
        reranked={panelTurn?.reranked}
      />
    </div>
  );
}