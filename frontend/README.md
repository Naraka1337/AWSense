# AWSense frontend

Vite + React + Tailwind CSS + Recharts dashboard. Runs on local fixtures, no backend needed.

```bash
npm install
npm run dev      # http://localhost:5173
npm run build
```

## Switching to the backend
Copy `.env.example` to `.env`, set `VITE_USE_MOCK=false`, and start FastAPI on `http://localhost:8000`.
All calls go through `src/services/api.js`. Fixtures live in `src/mock/`.

Expected endpoints (prefix `/api/v1`): `GET /overview`, `/resources`, `/alerts`, `/traffic`, `/recommendations`,
`POST /alerts/{id}/status` with body `{"status": "open" | "investigating" | "resolved" | "dismissed"}`,
`POST /recommendations/{id}/action` with body `{"action": "pending" | "approved" | "dismissed"}`,
and `POST /simulate` with body `{"scenario": "iam_breach" | "bot_traffic" | "resource_waste"}`.
