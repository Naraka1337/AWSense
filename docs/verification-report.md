# AWSense Verification Report

- **Date:** 2026-11-28
- **Branch:** `feat/task-4-live-refresh-alert-status-qa`
- **Base Commit:** `c94aa2a` (`Simulation 5-Factor Breakdown, Idempotency & Architecture Sync`)

---

## 1. Automated Build & Unit Tests

| Check | Command | Result | Details |
|---|---|---|---|
| Adapter unit tests | `node --test frontend/src/services/adapters.test.mjs` | **PASS** | `6 passed, 0 failed` (`219.85 ms`) |
| Production frontend build | `npm.cmd run build --prefix frontend` | **PASS** | `2192 modules transformed`, built in `9.41s` (`dist/index.html`, CSS `15.40 kB`, JS `630.81 kB`) |

---

## 2. Live 2-Server Walkthrough Environment

### Target Commands
```powershell
# Terminal 1 (Backend)
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --port 8000

# Terminal 2 (Frontend in Live Mode)
$env:VITE_USE_MOCK = "false"
npm.cmd run dev --prefix frontend
```

### Host Environment Notes
1. **Backend Port Substitution (`8000` → `8001`):** Binding `127.0.0.1:8000` on this Windows host failed with `[WinError 10013] An attempt was made to access a socket in a way forbidden by its access permissions` (port excluded/reserved by the host OS). Port `8001` bound cleanly, so the live 2-server verification ran with `uvicorn app.main:app --app-dir backend --port 8001` and `$env:VITE_USE_MOCK='false'; $env:VITE_API_URL='http://localhost:8001/api/v1'; npm.cmd run dev --prefix frontend -- --port 5173`.
2. **Browser Connection Availability:** Chrome DevTools remote debugging was inactive on this host (`ENOENT` on `C:\Users\ahmed\AppData\Local\Google\Chrome\User Data\DevToolsActivePort`), so the live 2-server walkthrough was executed programmatically against both running servers (probing Vite HTML/transformed JSX modules at `http://localhost:5173` and exercising every live FastAPI endpoint at `http://localhost:8001/api/v1` through the real `frontend/src/services/adapters.js` mappers and DB persistence readbacks) rather than via interactive Chrome DevTools clicking.

---

## 3. Live 2-Server Page & Flow Verification

### Vite Dev Server (`http://localhost:5173`, `VITE_USE_MOCK=false`)
- `GET /` returned `200 OK` serving the AWSense SPA entry HTML.
- Vite transformed and served all modified frontend modules with `200 OK` and zero compile errors:
  - `/src/components/Layout.jsx` (`onSimulated` prop wired to `setRefreshKey((k) => k + 1)`)
  - `/src/components/SimulatePanel.jsx` (`onSimulated?.()` invoked after live `POST /simulate`)
  - `/src/pages/Security.jsx` (`updateAlertStatus` and `Investigating` / `Resolve` / `Dismiss` / `Reopen` controls)
  - `/src/services/api.js` (`updateAlertStatus` and live `http://localhost:8001/api/v1` target)

### 5-Page Live API + Adapter Matrix (`http://localhost:8001/api/v1` → `adapters.js`)

| Page / Endpoint | Status | Observed Live Output |
|---|---|---|
| **Overview** (`GET /overview`) | **PASS** | `healthScore: 0`, `riskLevel: "CRITICAL"`, `monthlySavings: 2190.2`, `activeAlerts: { CRITICAL: 2, HIGH: 1, MEDIUM: 0, LOW: 0 }`, `trend: 30` daily points |
| **Resources** (`GET /resources`) | **PASS** | `14` total resources; `10` resources flagged by `Backup Gaps Only` (`backup === 'missing' \| 'stale'`); all 10 CSV export columns (`id`, `name`, `type`, `region`, `status`, `cpu`, `backup`, `lastBackup`, `monthlyCost`, `finding`) verified present |
| **Security** (`GET /alerts`) | **PASS** | `3` seeded alerts initially; selected `alert_inc_0001` for lifecycle verification |
| **Traffic** (`GET /traffic`) | **PASS** | `totalRequests: 2410000`, `botShare: 0.886` (`88.6%`), `costImpact: 138.2`, `timeline: 5` points, `patterns: 3` endpoints |
| **Recommendations** (`GET /recommendations`) | **PASS** | `5` seeded recommendations initially; selected `rec_0001` for action lifecycle verification |

### Interactive Mutation & Persistence Checks

| Flow | Steps Verified | Persistence & Result |
|---|---|---|
| **Alert Status Toggles** (`POST /alerts/{id}/status`) | Transitioned `alert_inc_0001` through `investigating` → `resolved` → `dismissed` → `open`; verified unknown ID returns HTTP `404` | **PASS** — Every transition returned `200 OK` and matched a fresh `GET /alerts` readback (simulating page reload) |
| **Recommendations Actions** (`POST /recommendations/{id}/action`) | Transitioned `rec_0001` through `approved` → `pending` (Undo) → `dismissed` → `pending` (Undo) | **PASS** — Every action returned `200 OK`, unwrapped cleanly via `adaptRecommendationAction`, and persisted across fresh `GET /recommendations` readbacks |
| **Resources Backup Gaps & CSV** | Verified `Backup Gaps Only` predicate (`missing`/`stale` = `10` of `14` resources) and validated all 10 fields consumed by `exportCsv()` in `Resources.jsx` | **PASS** |
| **Simulate Incident + Live Refresh** (`POST /simulate`) | Triggered `{"scenario": "iam_breach"}` (`risk_score: 68`, `severity: "high"`, `4` findings, `2` recommendations); verified `Layout.jsx` / `SimulatePanel.jsx` `onSimulated` → `refreshKey` wiring and re-queried `/alerts`, `/recommendations`, and `/overview` | **PASS** — `/alerts` grew `3 → 4` (`sim_alert_iam_breach` persisted), `/recommendations` grew `5 → 7` (`2` `sim_iam_breach_*` rows persisted), and `/overview` `activeAlerts.HIGH` updated `1 → 2` |
