/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async rewrites() {
    const backend = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
    // NOTE: /api/chat/stream is intentionally NOT here — it's served by the
    // Route Handler at src/app/api/chat/stream/route.ts, which streams SSE
    // unbuffered (rewrites buffer text/event-stream responses).
    return [
      { source: "/api/chat",   destination: `${backend}/chat`   },
      { source: "/api/health", destination: `${backend}/health` },
    ];
  },
};

module.exports = nextConfig;
