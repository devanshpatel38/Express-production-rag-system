// Streaming proxy for the backend SSE endpoint.
//
// Why a Route Handler instead of a next.config.js rewrite: rewrites proxy the
// response through Next's internal HTTP layer, which *buffers* `text/event-stream`
// responses — every event arrives in one chunk at the end, killing the live
// trace UX. A Route Handler lets us pipe the upstream ReadableStream straight to
// the client unbuffered, while staying same-origin (no CORS on the browser).

import type { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const BACKEND = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest) {
  const body = await req.text();

  const upstream = await fetch(`${BACKEND}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    // @ts-expect-error - `duplex` is required by Node's fetch for streaming bodies
    duplex: "half",
  });

  if (!upstream.ok || !upstream.body) {
    const text = await upstream.text().catch(() => upstream.statusText);
    return new Response(text || "upstream error", { status: upstream.status || 502 });
  }

  // Pipe the upstream SSE stream straight through, unbuffered.
  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}