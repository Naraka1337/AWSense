# AWSense Verification Report

- **Date:** 2026-11-28
- **Branch:** `main` (verified after commit `bb96d70` with Overview/main/Layout/docs alignment updates)

---

## 1. Automated Tests, ML Benchmark & Production Build

| Check | Command | Result | Details |
|---|---|---|---|
| Non-socket backend suites (8 modules) | `backend\.venv\Scripts\python.exe -m pytest backend\tests --ignore=backend\tests\test_api_routes.py --ignore=backend\tests\test_auditor_and_simulate.py -v` | **PASS** | `52 passed` (`16.14 s`) |
| FastAPI `TestClient` suites (2 modules) | `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_api_routes.py backend\tests\test_auditor_and_simulate.py -v` | **PASS** | `19 passed` (`31.48 s`), including `GET /api/v1/overview` ↔ `GET /api/v1/alerts` scoring parity assertions |
| Total backend suite | All 10 test modules (`backend/tests/`) | **71 / 71 PASS** | Zero failures across DB, repository, Boto3 stubber, correlator, ML/AI, eval, auditor/simulate, API routes, smoke |
| ML evaluation benchmark | `python -m app.services.ml_eval` (from `backend/`) | **PASS** | `precision: 1.0`, `recall: 1.0`, `f1: 1.0`, `fpr: 0.0`, `TN=119, FP=0, FN=0, TP=25`, `score_separation: 0.6255`, `34.29 ms` inference |
| Adapter unit tests | `node --test frontend/src/services/adapters.test.mjs` | **PASS** | `6 passed, 0 failed` (`117.16 ms`) |
| Production frontend build | `npm.cmd run build --prefix frontend` | **PASS** | `2192 modules transformed`, built in `9.86 s` (`dist/index.html`, CSS `15.40 kB`, JS `630.81 kB`) |

---

## 2. Live 2-Server Walkthrough Environment

### Target Commands
```powershell
# Terminal 1 (Backend)
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000

# Terminal 2 (Frontend in Live Mode)
$env:VITE_USE_MOCK = "false"
npm.cmd run dev --prefix frontend -- --port 5173
```

### Host Environment & Browser Availability Notes
1. **Local Server Startup:** Both `uvicorn` (`http://127.0.0.1:8000`) and Vite (`http://localhost:5173/`, `VITE_USE_MOCK=false`) started cleanly on this host. *(An earlier Task 4 run on another contributor host substituted port `8001` due to `WinError 10013`.)*
2. **Browser Connection Availability:** Chrome DevTools remote debugging was inactive on both QA hosts (`ENOENT` on Chrome `DevToolsActivePort`), so automated browser clicking through the rendered UI could not connect. Automated HTTP/FastAPI + SQLite lifecycle checks verified backend-adapter behavior; an interactive real-browser click-through remains pending until `chrome://inspect/#remote-debugging` is enabled or run manually at `http://localhost:5173/`.

---

## 3. Verified Live API, Persistence & Scoring Parity

### Overview ↔ Security Parity Check (Post-Fix)
`overview.py` now delegates active-alert scoring to `alerts.score_alerts()` instead of reading uncalibrated stored correlator scores directly:

| Endpoint | Observed Output (Fresh Seeded SQLite DB) |
|---|---|
| `GET /api/v1/overview` | `health_score: 16.7`, `risk_level: "high"`, `total_monthly_savings_usd: 2190.2`, `monthly_spend_usd: 3165.75`, `active_alerts: { total: 3, critical: 0, high: 1, medium: 1, low: 1 }`, `monitored_resources: 14`, `unprotected_resources: 10`, `cost_usage_trend: 30 days` |
| `GET /api/v1/alerts` | `alert_inc_0001`: `83.32` (`high`, `ml_score: 0.8094`), `alert_inc_0002`: `58.87` (`medium`, `ml_score: 0.7736`), `alert_backup_db-prod-orders-01`: `37.53` (`low`, `ml_score: 0.3477`) |
| `GET /api/v1/resources` | `14` total resources (`total_monthly_cost_usd: 3165.75`, `unprotected_count: 10`, `underutilized_count: 2`) |

### Earlier Task 4 Endpoint, Persistence & UI Wiring Matrix
*(Recorded in Task 4 PR #14 on the live 2-server HTTP walkthrough and re-verified via `test_api_routes.py` and `test_auditor_and_simulate.py`)*

| Flow | Steps Verified | Persistence & Result |
|---|---|---|
| **Traffic Analytics** (`GET /traffic`) | Verified `2410000` requests, `88.6%` bot share, `$138.2` cost impact, `5` timeline points, `3` flagged patterns | **PASS** |
| **Alert Status Toggles** (`POST /alerts/{id}/status`) | Transitioned `open` → `investigating` → `resolved` → `dismissed` → `open`; verified `404` on unknown ID and `422` on invalid status | **PASS** — Persists in SQLite across fresh `GET /alerts` reads and `Security.jsx` controls |
| **Recommendations Actions** (`POST /recommendations/{id}/action`) | Transitioned `pending` → `approved` → `pending` (Undo) → `dismissed` → `pending` (Undo); verified `404` and `422` | **PASS** — Persists across fresh `GET /recommendations` reads |
| **Resources Backup Gaps & CSV** | Verified `10` of `14` unprotected resources and CSV column/sanitization pipeline | **PASS** |
| **Simulate Incident + Idempotency** (`POST /simulate`) | Triggered `iam_breach` (`68 high`), `bot_traffic` (`51 medium`), `resource_waste` (`54 medium`); verified `5`-factor `signal_breakdown`, idempotent `sim_*` recommendations across repeated calls, and `Layout.jsx` → `SimulatePanel.jsx` `onSimulated` refresh wiring | **PASS** |
