import Link from "next/link";
import Image from "next/image";

const GITHUB_URL = "https://github.com/devanshpatel38/Express-production-rag-system";

async function getHealth() {
  try {
    const base = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
    const res = await fetch(`${base}/health`, { next: { revalidate: 60 } });
    if (!res.ok) return null;
    return res.json() as Promise<{ indexed_chunks: number; llm_provider: string }>;
  } catch {
    return null;
  }
}
const PORTFOLIO_URL = "https://portfolio-website-umber-ten-90.vercel.app/#";

const QUESTIONS = [
  { kind: "Routing",   text: "How do I set up middleware in Express?",             chunks: 4 },
  { kind: "Errors",    text: "How does error-handling middleware work?",            chunks: 4 },
  { kind: "Static",    text: "How do I serve static files from a directory?",      chunks: 3 },
  { kind: "Lifecycle", text: "What's the difference between app.use and app.get?", chunks: 3 },
];

function ArrowIcon() {
  return (
    <svg viewBox="0 0 14 14" fill="none" width="14" height="14">
      <path d="M3 7h8M7 3l4 4-4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
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

export default async function LandingPage() {
  const health = await getHealth();
  const chunkCount = health?.indexed_chunks?.toLocaleString() ?? "—";
  return (
    <>
      {/* ─── Nav ─── */}
      <nav className="lp-nav">
        <div className="lp-nav-inner">
          <Link href="/" className="lp-brand">
            <span className="lp-brand-logo">
              <Image src="/cogito-logo-short.svg" alt="" width={26} height={14} />
            </span>
            <span>Express Docs</span>
            <span className="lp-brand-tag">RAG</span>
          </Link>
          <div className="lp-nav-links">
            <a href="#how-it-works" className="lp-nav-link hide-sm">How it works</a>
            <a href="https://expressjs.com" target="_blank" rel="noopener noreferrer" className="lp-nav-link hide-sm">Express.js docs</a>
            <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer" className="lp-nav-link hide-sm">GitHub</a>
            <Link href="/chat" className="lp-nav-cta">
              Open chat <ArrowIcon />
            </Link>
          </div>
        </div>
      </nav>

      {/* ─── Page body ─── */}
      <main className="lp-page">

        {/* Hero */}
        <section className="lp-hero">
          <div className="lp-eyebrow">
            <span className="pulse" />
            <strong>{chunkCount} chunks</strong>
            <span className="chip-divider" />
            <span className="mono">expressjs/express @ v5.0.1</span>
          </div>
          <h1 className="lp-hero-title">
            Ask the Express.js docs{" "}
            <span className="accent">in plain English.</span>
          </h1>
          <p className="lp-hero-sub">
            A retrieval-augmented chat grounded in the official Express.js documentation.
            Answers cite the exact file and line range, so you always know where they came from.
          </p>
          <div className="lp-hero-actions">
            <Link href="/chat" className="lp-btn-primary">
              Open the chat <ArrowIcon />
            </Link>
            <a href="#try-it" className="lp-btn-secondary">
              Try a sample question
            </a>
          </div>
        </section>

        {/* Try it */}
        <section className="lp-section" id="try-it">
          <div className="lp-section-head">
            <div className="lp-section-overline">Try it</div>
            <h2 className="lp-section-title">Pick a question to see it in action</h2>
            <p className="lp-section-sub">Selecting one opens the chat with that question pre-asked.</p>
          </div>

          <div className="lp-q-grid">
            {QUESTIONS.map((q) => (
              <Link
                key={q.text}
                href={`/chat?q=${encodeURIComponent(q.text)}`}
                className="lp-q-card"
              >
                <div className="lp-q-card-top">
                  <span className="lp-q-kind">
                    <span className="dot" />
                    {q.kind}
                  </span>
                  <span className="lp-q-card-arrow">
                    <ArrowIcon />
                  </span>
                </div>
                <p className="lp-q-text">{q.text}</p>
                <div className="lp-q-meta">
                  <span>{q.chunks} chunks</span>
                  <span className="sep" />
                  <span>~1.1s latency</span>
                  <span className="sep" />
                  <span>reranked</span>
                </div>
              </Link>
            ))}
          </div>
        </section>

        {/* How it works */}
        <section className="lp-section" id="how-it-works" style={{ paddingTop: 0 }}>
          <div className="lp-section-head">
            <div className="lp-section-overline">How it works</div>
            <h2 className="lp-section-title">Four steps, on every question</h2>
          </div>
          <div className="lp-how">
            <div className="lp-how-step">
              <div className="lp-how-num"><strong>01</strong> Embed</div>
              <div className="lp-how-title">Vector search</div>
              <p className="lp-how-desc">Your query is embedded and matched against <code>{chunkCount}</code> indexed chunks of the Express docs.</p>
            </div>
            <div className="lp-how-step">
              <div className="lp-how-num"><strong>02</strong> Retrieve</div>
              <div className="lp-how-title">Top-20 candidates</div>
              <p className="lp-how-desc">The closest chunks are pulled with their file path and line range preserved as metadata.</p>
            </div>
            <div className="lp-how-step">
              <div className="lp-how-num"><strong>03</strong> Rerank</div>
              <div className="lp-how-title">Semantic re-order</div>
              <p className="lp-how-desc">A cross-encoder reranks for semantic fit. Optional — toggle off for raw <code>k-NN</code> results.</p>
            </div>
            <div className="lp-how-step">
              <div className="lp-how-num"><strong>04</strong> Generate</div>
              <div className="lp-how-title">Cited answer</div>
              <p className="lp-how-desc">The model writes the answer grounded in the top chunks, with every claim citable to a source.</p>
            </div>
          </div>
        </section>

      </main>

      {/* ─── Footer ─── */}
      <footer className="lp-footer">
        <div className="lp-footer-inner">
          <div className="lp-footer-left">
            <span className="status-dot" />
            <span>Index healthy · expressjs/express</span>
          </div>
          <div className="lp-footer-right">
            <Link href="/chat">Chat</Link>
            <span className="sep">·</span>
            <a href="https://expressjs.com" target="_blank" rel="noopener noreferrer">Express.js</a>
            <span className="sep">·</span>
            <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer">GitHub</a>
            <span className="sep">·</span>
            <a href={PORTFOLIO_URL} target="_blank" rel="noopener noreferrer">devanshpatel.com</a>
          </div>
        </div>
      </footer>
    </>
  );
}