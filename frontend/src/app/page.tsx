"use client";

import { useEffect, useRef, useState } from "react";
import { Globe, ExternalLink } from "lucide-react";
import { chat, type ChatMessage, type Source } from "@/lib/api";
import { MessageBubble } from "@/components/MessageBubble";
import { StatusPill } from "@/components/StatusPill";

interface Turn extends ChatMessage {
  sources?: Source[];
  latency_ms?: number;
}

const STARTER_QUESTIONS = [
  "How do I define a GET route?",
  "What is the difference between req.query and req.params?",
  "How do I write error-handling middleware?",
  "Serve static files from a directory called public",
];

const TECH_TAGS = [
  "Next.js",
  "TypeScript",
  "RAG",
  "BM25 + Dense",
  "Cross-Encoder",
];

const GITHUB_URL = "https://github.com/devanshpatel38/Express-production-rag-system";
const PORTFOLIO_URL = "https://portfolio-website-umber-ten-90.vercel.app/#";

export default function Page() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [useReranker, setUseReranker] = useState(true);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns.length, busy]);

  function GithubIcon({ size = 13 }: { size?: number }) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="currentColor"
        aria-hidden="true"
      >
        <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z" />
      </svg>
    );
  }

  async function send(query: string) {
    const q = query.trim();
    if (!q || busy) return;
    setError(null);
    const newTurns: Turn[] = [...turns, { role: "user", content: q }];
    setTurns(newTurns);
    setInput("");
    setBusy(true);
    try {
      const history: ChatMessage[] = newTurns.map(({ role, content }) => ({
        role,
        content,
      }));
      const resp = await chat(q, history.slice(0, -1), { useReranker });
      setTurns((prev) => [
        ...prev,
        {
          role: "assistant",
          content: resp.answer,
          sources: resp.sources,
          latency_ms: resp.latency_ms,
        },
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    send(input);
  }

  return (
    <main className="relative mx-auto max-w-3xl px-5 sm:px-8 pt-10 pb-40 min-h-screen">
      {/* Masthead */}
      <header className="mb-12 relative">
        {/* Top bar: issue label + branding links + status */}
        <div className="flex items-center justify-between text-[10px] font-mono uppercase tracking-[0.22em] text-muted">
          <span>Volume I · Issue 01</span>

          <div className="flex items-center gap-5">
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 hover:text-ink transition-colors"
              aria-label="GitHub repository"
            >
              <GithubIcon size={12} />
              <span className="hidden sm:inline">Source</span>
            </a>
            <a
              href={PORTFOLIO_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 hover:text-ink transition-colors"
              aria-label="Portfolio website"
            >
              <Globe size={12} strokeWidth={1.8} />
              <span className="hidden sm:inline">Portfolio</span>
            </a>
            <StatusPill />
          </div>
        </div>

        <div className="h-px bg-ink mt-2 mb-6" />

        <h1 className="font-serif text-5xl sm:text-6xl leading-[0.95] tracking-tight">
          Express,
          <br />
          <span className="italic text-accent">in conversation</span>.
        </h1>

        <p className="mt-5 max-w-xl text-[15px] leading-relaxed text-ink/80">
          A retrieval-augmented chat over the official{" "}
          <a
            href="https://github.com/expressjs/expressjs.com"
            target="_blank"
            rel="noopener noreferrer"
            className="underline decoration-accent/60 underline-offset-4 hover:text-accent"
          >
            Express.js documentation
          </a>
          . Hybrid search (dense + BM25), cross-encoder reranking, grounded
          answers with citations.
        </p>

        {/* Tech stack pills */}
        <div className="flex flex-wrap gap-2 mt-5">
          {TECH_TAGS.map((tag) => (
            <span
              key={tag}
              className="text-[10px] font-mono uppercase tracking-[0.18em] border border-rule px-2 py-0.5 text-muted"
            >
              {tag}
            </span>
          ))}
        </div>

        {/* Inline CTA links — useful for recruiters reading the UI */}
        <div className="flex items-center gap-5 mt-5">
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-[12px] font-mono underline underline-offset-4 decoration-rule hover:text-accent hover:decoration-accent transition-colors"
          >
            <GithubIcon size={12} />
            View on GitHub
            <ExternalLink size={10} strokeWidth={1.8} className="opacity-60" />
          </a>
          <a
            href={PORTFOLIO_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-[12px] font-mono underline underline-offset-4 decoration-rule hover:text-accent hover:decoration-accent transition-colors"
          >
            <Globe size={13} strokeWidth={1.8} />
            devanshpatel.com
            <ExternalLink size={10} strokeWidth={1.8} className="opacity-60" />
          </a>
        </div>
      </header>

      {/* Starter cards (only before the first turn) */}
      {turns.length === 0 && (
        <section className="mb-12">
          <div className="text-[10px] font-mono uppercase tracking-[0.22em] text-muted mb-3">
            Try
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {STARTER_QUESTIONS.map((q) => (
              <button
                key={q}
                onClick={() => send(q)}
                className="text-left font-serif text-[15px] leading-snug border border-rule bg-paper/60 hover:bg-paper hover:border-accent transition-colors px-4 py-3 rounded-sm"
              >
                <span className="text-accent mr-2">→</span>
                {q}
              </button>
            ))}
          </div>
        </section>
      )}

      {/* Conversation */}
      <section className="space-y-10">
        {turns.map((t, i) => (
          <MessageBubble
            key={i}
            role={t.role}
            content={t.content}
            sources={t.sources}
            latency_ms={t.latency_ms}
          />
        ))}
        {busy && (
          <div className="font-mono text-[11px] uppercase tracking-[0.18em] text-muted">
            retrieving<span className="animate-blink">_</span>
          </div>
        )}
        {error && (
          <div className="border border-red-700/40 bg-red-50/40 px-4 py-3 text-sm text-red-900 rounded-sm">
            {error}
          </div>
        )}
        <div ref={endRef} />
      </section>

      {/* Footer */}
      <footer className="mt-20 border-t border-rule pt-6 flex items-center justify-between text-[10px] font-mono uppercase tracking-[0.18em] text-muted">
        <span>
          Built by{" "}
          <a
            href={PORTFOLIO_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-ink transition-colors underline underline-offset-2"
          >
            Devansh Patel
          </a>
        </span>
        <a
          href={GITHUB_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1.5 hover:text-ink transition-colors"
        >
          <GithubIcon size={12} />
          View on GitHub
        </a>
      </footer>

      {/* Composer (fixed bottom) */}
      <form
        onSubmit={onSubmit}
        className="fixed inset-x-0 bottom-0 pointer-events-none"
      >
        <div className="pointer-events-auto mx-auto max-w-3xl px-5 sm:px-8 pb-6 pt-10 bg-gradient-to-t from-paper via-paper/95 to-transparent">
          <div className="flex items-center justify-between mb-2">
            <label className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-[0.18em] text-muted cursor-pointer">
              <input
                type="checkbox"
                checked={useReranker}
                onChange={(e) => setUseReranker(e.target.checked)}
                className="accent-accent"
              />
              reranker
            </label>
            <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-muted">
              press ↵ to send
            </span>
          </div>
          <div className="flex gap-2 border border-ink bg-paper">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about routing, middleware, error handling…"
              disabled={busy}
              className="flex-1 bg-transparent px-4 py-3 outline-none font-serif text-[16px] placeholder:text-muted/70"
            />
            <button
              type="submit"
              disabled={busy || !input.trim()}
              className="px-5 bg-ink text-paper font-mono text-[11px] uppercase tracking-[0.18em] disabled:opacity-40 hover:bg-accent transition-colors"
            >
              Ask
            </button>
          </div>
        </div>
      </form>
    </main>
  );
}