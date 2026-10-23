# Frontend

The web UI for the Global Economic Prospects RAG chatbot. It is a Next.js 14 (App
Router) app with a landing page and a chat page. Answers stream in live, and each
answer comes with a sources panel showing the page, units and score of the chunks
it was built from.

## Layout

```
frontend/
├── src/
│   ├── app/
│   │   ├── layout.tsx                # Fonts and page shell
│   │   ├── page.tsx                  # Landing page (shows the indexed chunk count)
│   │   ├── chat/page.tsx             # Chat UI (Client Component, SSE streaming)
│   │   ├── api/chat/stream/route.ts  # Route Handler: passes the backend SSE stream through
│   │   └── globals.css               # Design tokens and component styles
│   ├── components/
│   │   ├── MessageBubble.tsx         # One assistant turn: answer and sources trigger
│   │   ├── SourcesPanel.tsx          # Slide-in panel of retrieved sources
│   │   └── StatusPill.tsx            # Backend health indicator
│   └── lib/
│       └── api.ts                    # Typed client: chat(), chatStream(), health()
├── next.config.js                    # /api/chat and /api/health rewrites
├── tailwind.config.js
└── .env.example
```

## Routes

| Route | What |
| --- | --- |
| `/` | Landing page. Reads `/health` for the indexed chunk count. |
| `/chat` | Chat interface. `?q=<question>` asks a question on load. |

## How it talks to the backend

The browser only calls same-origin `/api` paths, so no CORS setup is needed:

- `/api/chat` and `/api/health` are rewrites in `next.config.js` that forward to the
  backend's `/chat` and `/health`.
- `/api/chat/stream` is a Route Handler (`src/app/api/chat/stream/route.ts`) that
  passes the backend's Server-Sent Events stream straight through. It is a Route
  Handler rather than a rewrite because rewrites buffer `text/event-stream`
  responses.

`src/lib/api.ts` holds all backend calls. `chatStream()` POSTs to `/api/chat/stream`
and parses the event stream, calling `onToken` as answer text arrives and returning
the final answer with its sources.

## Chat features

- **Token streaming** — the answer appears as it is generated.
- **Sources panel** — lists the retrieved chunks with their page, units, chunk type
  (prose, table row or figure) and score.
- **Composer toggles** — `reranker` turns Cohere reranking on or off, and `stream`
  switches between SSE streaming and the single `/chat` call.

## Local dev

```bash
npm install
cp .env.example .env.local   # set NEXT_PUBLIC_API_BASE_URL
npm run dev
```

Open http://localhost:3000. The backend should be running on the address set in
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
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | Backend address the `/api` proxy forwards to. It is baked in at build time, so rebuild after changing it. |

## License

MIT
