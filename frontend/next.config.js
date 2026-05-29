/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async rewrites() {
    const backend = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
    return [
      { source: "/api/chat",   destination: `${backend}/chat`   },
      { source: "/api/health", destination: `${backend}/health` },
    ];
  },
};

module.exports = nextConfig;
