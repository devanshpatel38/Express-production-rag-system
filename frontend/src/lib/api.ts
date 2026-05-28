// Small typed wrapper around the backend. Keeping this isolated means swapping
// transports (REST -> WebSocket streaming, later) only touches one file.

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

export interface ChatResponse {
  answer: string;
  sources: Source[];
  latency_ms: number;
}

export interface HealthResponse {
  status: "ok" | "degraded";
  indexed_chunks: number;
  llm_provider: string;
  reranker_enabled: boolean;
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function chat(
  query: string,
  history: ChatMessage[],
  opts?: { useReranker?: boolean }
): Promise<ChatResponse> {
  const resp = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      history,
      use_reranker: opts?.useReranker,
    }),
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => resp.statusText);
    throw new Error(`Chat failed (${resp.status}): ${text}`);
  }
  return resp.json();
}

export async function health(): Promise<HealthResponse> {
  const resp = await fetch(`${API_BASE}/health`, { cache: "no-store" });
  if (!resp.ok) throw new Error(`Health check failed: ${resp.status}`);
  return resp.json();
}
