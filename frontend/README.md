# Frontend

Next.js 14 (App Router) UI. Talks to the backend via REST.

## Layout

```
frontend/
├── src/
│   ├── app/
│   │   ├── layout.tsx       # Fonts (Fraunces / Inter / JetBrains Mono)
│   │   ├── page.tsx         # Chat page (the only route)
│   │   └── globals.css
│   ├── components/
│   │   ├── MessageBubble.tsx
│   │   └── StatusPill.tsx
│   └── lib/
│       └── api.ts           # Typed client for /chat + /health
├── package.json
├── next.config.js
├── tailwind.config.js
└── .env.example
```

## Local dev

```bash
npm install
cp .env.example .env.local
npm run dev
```

Open http://localhost:3000.

## Environment

| Variable | Default | Notes |
| --- | --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | Must point at the backend. Note the `NEXT_PUBLIC_` prefix is required for client-side access. |

## Design notes

The UI leans editorial — Fraunces (variable serif with optical sizing) for
display, Inter for body, JetBrains Mono for metadata. Warm off-white paper
background with subtle SVG noise. Burnt-orange accent reads as "Express"
without literally using their logo color.

It's intentionally a single page with a fixed-bottom composer; no sidebar,
no settings drawer. The reranker toggle is the only visible knob — everything
else is in the API's `top_k` / `use_reranker` overrides for the eval harness.
