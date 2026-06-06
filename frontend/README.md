# Frontend

Next.js 14 (App Router) UI. Talks to the backend through a same-origin `/api`
proxy (no CORS), and streams answers live over Server-Sent Events.

## Layout

```
frontend/
├── src/
│   ├── app/
│   │   ├── layout.tsx                # Fonts (DM Sans / JetBrains Mono)
│   │   ├── page.tsx                  # Landing page (Server Component, dynamic chunk count)
│   │   ├── chat/page.tsx             # Chat UI (Client Component, SSE streaming)
│   │   ├── api/chat/stream/route.ts  # Route Handler: pipes backend SSE through unbuffered
│   │   └── globals.css               # Cogito design tokens + all component styles
│   ├── components/
│   │   ├── MessageBubble.tsx         # Assistant turn: answer, live stage, trace, sources trigger
│   │   ├── HealingTrace.tsx          # Collapsible self-healing timeline + badges
│   │   └── SourcesPanel.tsx          # Slide-in retrieved-sources panel
│   └── lib/
│       └── api.ts                    # Typed client: chat(), chatStream() SSE parser, health()
├── package.json
├── next.config.js                    # /api/chat + /api/health rewrites
├── tailwind.config.js
└── .env.example
```

## Routes

| Route | Type | What |
| --- | --- | --- |
| `/` | Server Component | Landing page; fetches `/health` for the live chunk count (ISR, 60s) |
| `/chat` | Client Component | Chat interface; supports `?q=<question>` to auto-ask on load |

## How requests reach the backend

The browser never calls the backend directly — every call is same-origin under
`/api`, so there's no CORS dependency:

- `/api/chat` and `/api/health` → simple **rewrites** in `next.config.js`.
- `/api/chat/stream` → a **Route Handler** (`app/api/chat/stream/route.ts`) that
  pipes the upstream SSE stream straight through. This *cannot* be a rewrite:
  Next.js rewrites buffer `text/event-stream` responses, which would make every
  healing event arrive at once and kill the live trace.

## Local dev

```bash
npm install
cp .env.example .env.local   # set NEXT_PUBLIC_API_BASE_URL
npm run dev
```

Open http://localhost:3000.

## Environment

| Variable | Default | Notes |
| --- | --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | Backend origin the `/api` proxy forwards to. `NEXT_PUBLIC_` is **baked in at build time** — on Vercel you must redeploy after changing it. |

## Chat features

- **Live healing trace** — each pipeline stage (route → retrieve → grade →
  rewrite → verify → done) renders as a timeline under the answer, with
  `cached` / `fallback` / `N attempts` badges.
- **Token streaming** — the answer streams in with a blinking cursor.
- **Composer toggles** — `reranker`, `hyde`, and `stream` (SSE on/off). Turning
  `stream` off uses the synchronous `/chat` call and renders the full trace once
  the answer arrives.
- **Sources panel** — slide-in panel listing the retrieved chunks with scores.

## Design notes

Cogito design system — DM Sans for UI, JetBrains Mono for metadata, Chathams
Blue (`#156082`) accent on a light surface. Landing-page styles are namespaced
with an `lp-` prefix and the self-healing trace with an `ht-` prefix so the two
routes share one stylesheet without collisions.