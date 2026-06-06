// Small typed wrapper around the backend. Keeping this isolated means swapping
// transports (REST <-> SSE) only touches one file.
//
// All calls go through the Next.js rewrite proxy at /api/* (see next.config.js)
// so the browser never crosses origins — no CORS dependency on the backend.

export type Role = "user" | "assistant";

export interface ChatMessage {
  role: Role;
  content: string;
}

export interface Source {
  chunk_id: string;
  source_path: string;
  title: string;
  snippet: string;
  score: number;
}

// Mirrors backend HealingEvent (app/models/schemas.py).
export type HealingStage =
  | "routing"
  | "cache_hit"
  | "hyde"
  | "retrieval"
  | "grading"
  | "rerank"
  | "rewrite"
  | "generation"
  | "faithfulness"
  | "retry"
  | "give_up"
  | "done";

export interface HealingEvent {
  stage: HealingStage;
  attempt: number;
  message: string;
  score?: number | null;
  detail?: Record<string, unknown> | null;
}

export interface ChatResponse {
  answer: string;
  sources: Source[];
  latency_ms: number;
  trace: HealingEvent[];
  from_cache: boolean;
  fallback: boolean;
  attempts: number;
}

export interface HealthResponse {
  status: "ok" | "degraded";
  indexed_chunks: number;
  llm_provider: string;
  reranker_enabled: boolean;
  self_healing_enabled: boolean;
}

const API_BASE = "/api";

interface ChatOpts {
  useReranker?: boolean;
  useSelfHealing?: boolean;
  useHyde?: boolean;
}

export async function chat(
  query: string,
  history: ChatMessage[],
  opts?: ChatOpts
): Promise<ChatResponse> {
  const resp = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      history,
      use_reranker: opts?.useReranker,
      use_self_healing: opts?.useSelfHealing,
      use_hyde: opts?.useHyde,
    }),
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => resp.statusText);
    throw new Error(`Chat failed (${resp.status}): ${text}`);
  }
  return resp.json();
}

// --- Streaming ---
// The backend emits Server-Sent Events on /chat/stream. We can't use the native
// EventSource API because it only supports GET. Instead we POST and parse the
// stream by hand. The callbacks fire as events arrive; the returned promise
// resolves with the final ChatResponse-shaped payload.

export interface StreamCallbacks {
  onEvent?: (event: HealingEvent) => void;
  onToken?: (text: string) => void;
  onError?: (message: string) => void;
}

export async function chatStream(
  query: string,
  history: ChatMessage[],
  opts: ChatOpts | undefined,
  callbacks: StreamCallbacks
): Promise<ChatResponse> {
  const resp = await fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      history,
      use_reranker: opts?.useReranker,
      use_hyde: opts?.useHyde,
    }),
  });
  if (!resp.ok || !resp.body) {
    const text = await resp.text().catch(() => resp.statusText);
    throw new Error(`Stream failed (${resp.status}): ${text}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let final: ChatResponse | null = null;

  // SSE format: `event: <type>\ndata: <json>\n\n`. We accumulate until we hit
  // a blank line, then parse one event at a time.
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);

      let evType = "message";
      let dataLine = "";
      for (const line of raw.split("\n")) {
        if (line.startsWith("event:")) evType = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLine += line.slice(5).trim();
      }
      if (!dataLine) continue;
      let payload: any;
      try {
        payload = JSON.parse(dataLine);
      } catch {
        continue;
      }

      if (evType === "event") callbacks.onEvent?.(payload as HealingEvent);
      else if (evType === "token") callbacks.onToken?.(payload.text);
      else if (evType === "final") final = payload as ChatResponse;
      else if (evType === "error") {
        const msg = payload.message ?? "stream error";
        callbacks.onError?.(msg);
        throw new Error(msg);
      }
    }
  }

  if (!final) throw new Error("Stream ended without a final payload");
  return final;
}

export async function health(): Promise<HealthResponse> {
  const resp = await fetch(`${API_BASE}/health`, { cache: "no-store" });
  if (!resp.ok) throw new Error(`Health check failed: ${resp.status}`);
  return resp.json();
}