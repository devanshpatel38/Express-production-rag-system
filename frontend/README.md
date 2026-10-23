# Frontend

The web UI for the GPO Annual Report chatbot, built with Next.js 14 (App Router).
It has a landing page and a chat page. Questions go to the backend, and answers
stream back live with a sources panel showing the page, units, and score of each
retrieved chunk.

## Layout

```
frontend/
├── src/
│   ├── app/
│   │   ├── layout.tsx                # Fonts (DM Sans / JetBrains Mono)
│   │   ├── page.tsx                  # Landing page (Server Component)
│   │   ├── chat/page.tsx             # Chat UI (Client Component, SSE streaming)
│   │   ├── api/chat/stream/route.ts  # Route Handler: passes the backend SSE stream through
│   │   └── globals.css               # Design tokens and component styles
│   ├── components/
│   │   ├── MessageBubble.tsx         # One assistant turn: answer and sources trigger
│   │   ├── SourcesPanel.tsx          # Slide-in panel of retrieved sources
│   │   └── StatusPill.tsx            # Status indicator
│   └── lib/
│       └── api.ts                    # Typed client: chat(), chatStream(), health()
├── package.json
├── next.config.js                    # /api/chat and /api/health rewrites
├── tailwind.config.js
└── .env.example
```

## Routes

| Route | Type | What |
| --- | --- | --- |
| `/` | Server Component | Landing page; reads `/health` for the indexed chunk count (refreshed every 60s) |
| `/chat` | Client Component | Chat interface; `?q=<question>` asks a question on load |

## How requests reach the backend

The browser calls everything under `/api` on the same origin:

- `/api/chat` and `/api/health` are rewrites in `next.config.js` that forward to the
  backend's `/chat` and `/health`.
- `/api/chat/stream` is a Route Handler (`src/app/api/chat/stream/route.ts`) that
  passes the backend's Server-Sent Events stream straight through, so tokens and
  sources reach the page as they are produced. It is a Route Handler because
  Next.js rewrites buffer `text/event-stream` responses.

## Local dev

```bash
npm install
cp .env.example .env.local   # set NEXT_PUBLIC_API_BASE_URL
npm run dev
```

Open http://localhost:3000. The backend should be running on the address in
`NEXT_PUBLIC_API_BASE_URL`.

## Scripts

| Command | What it does |
| --- | --- |
| `npm run dev` | Start the dev server |
| `npm run build` | Production build |
| `npm run start` | Serve the production build |
| `npm run lint` | Run ESLint |
| `npm run typecheck` | Run `tsc --noEmit` |

## Environment

| Variable | Default | Notes |
| --- | --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | Backend origin that the `/api` proxy forwards to. It is baked in at build time, so rebuild after changing it. |

## Chat features

- **Token streaming** - the answer streams in as it is generated.
- **Composer toggles** - `reranker` turns the Cohere rerank step on or off, and
  `stream` switches between streaming (`/api/chat/stream`) and a single response
  (`/api/chat`).
- **Sources panel** - lists the chunks behind an answer with their page, units,
  and score.

## Design notes

DM Sans for the interface and JetBrains Mono for metadata, with a blue accent on a
light surface. Landing-page styles use an `lp-` prefix so both routes share one
stylesheet without collisions.

## License

MIT
