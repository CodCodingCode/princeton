# NeoVax frontend

Next.js 15 + Tailwind dashboard for the NeoVax pathology-PDF → NCCN-railway
flow. Talks to the FastAPI backend over JSON + Server-Sent Events.

## Setup

```bash
cd frontend
npm install
cp .env.example .env.local       # optional — fill in Google Maps key
npm run dev                       # http://localhost:3000
```

The backend must be running on port 8000 (`neoantigen serve` in `backend/`).
`next.config.mjs` proxies `/api/*` → `${NEOVAX_BACKEND_URL}` so CORS never
matters in dev.

## Pages

- `/upload` — PDF drop zone. POSTs to `/api/cases`, redirects to `/case/<id>`.
- `/case/<id>` — live dashboard: extracted fields, Mermaid railway + per-node
  alternatives, matched trials, Google Maps trial-site view, Kimi K2 chat,
  pipeline event log, downloadable oncologist report.

## Google Maps fallback

When `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` is unset, `TrialMap` degrades to a
text list of sites — the rest of the flow is unaffected.
