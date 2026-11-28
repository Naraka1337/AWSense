# AWSense Verification Report

- **Date:** 2026-11-28
- **Branch:** `main` (verified through commit `ca80613` with live 2-server Google Chrome E2E walkthrough)

---

## 1. Automated Tests, ML Benchmark & Production Build

| Check | Command | Result | Details |
|---|---|---|---|
| Task 5 smoke suite | `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_codebase_smoke.py -v` | **PASS** | `5 passed` (`21.72 s`), including `/alerts/{id}/status`, `ml_eval`, `get_telemetry_provider("aws")`, and `SimulatePanel` contract checks |
| Non-socket backend suites (8 modules) | `backend\.venv\Scripts\python.exe -m pytest backend\tests --ignore=backend\tests\test_api_routes.py --ignore=backend\tests\test_auditor_and_simulate.py -v` | **PASS** | `54 passed` (`17.52 s`) |
| FastAPI `TestClient` suites (2 modules) | `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_api_routes.py backend\tests\test_auditor_and_simulate.py -v` | **PASS** | `19 passed` (`31.48 s`), including `GET /api/v1/overview` ↔ `GET /api/v1/alerts` scoring parity assertions *(run prior to Task 5 doc/smoke additions on identical app/router code)* |
| Total backend suite | All 10 test modules (`backend/tests/`) | **73 / 73 PASS** | Zero failures across DB, repository, Boto3 stubber, correlator, ML/AI, eval, auditor/simulate, API routes, smoke |
| ML evaluation benchmark | `python -m app.services.ml_eval` (from `backend/`) | **PASS** | `precision: 1.0`, `recall: 1.0`, `f1: 1.0`, `fpr: 0.0`, `TN=119, FP=0, FN=0, TP=25`, `score_separation: 0.6255`, `34.29 ms` inference |
| Adapter unit tests | `node --test frontend/src/services/adapters.test.mjs` | **PASS** | `6 passed, 0 failed` (`135.17 ms`) |
| Production frontend build | `npm.cmd run build --prefix frontend` | **PASS** | `2192 modules transformed`, built in `14.62 s` (`dist/index.html`, CSS `15.40 kB`, JS `630.81 kB`) |

---

## 2. Live Two-Server & Google Chrome Browser Environment

```powershell
# Terminal 1 (Backend, fresh seeded SQLite DB)
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000

# Terminal 2 (Frontend in Live Mode)
$env:VITE_USE_MOCK = "false"
npm.cmd run dev --prefix frontend -- --port 5173
```

- Both servers bound cleanly on standard ports (`http://127.0.0.1:8000` and `http://localhost:5173/`).
- Connected **Google Chrome** over Chrome DevTools Protocol (`chrome://inspect/#remote-debugging`) and executed a complete interactive click-through across all 5 views, reload persistence checks, and the simulation drawer.
- **Console & Network Audit:** Every `/api/v1/*` request returned **HTTP `200 OK`**. Zero JavaScript runtime errors, zero React errors, and zero failed API calls occurred (only non-application `/favicon.ico` 404 and informational React Router v6 future-flag warnings).

---

## 3. Verified Live Chrome UI Matrix

| Page / Flow | Actions & Assertions Verified in Live Chrome | Result |
|---|---|---|
| **Overview** (`/`) | Verified **`Live data`** pill and `"Account 4821-0093-1175 · us-east-1 and ap-southeast-1"` caption; `Cloud health: 17/100` (`Latest average CPU: 89%`), `Active alerts: 3` (`0 critical, 1 high`), `Monthly savings available: $2,190`, `Risk level: High` (`1 active at this severity`); severity bars (`0 / 1 / 1 / 1`) and 30-day Recharts `ComposedChart` (`Oct 23`–`Nov 17`) rendered cleanly | **PASS** |
| **Resources** (`/resources`) | Verified `Resource inventory (14)` and `10 resources have a backup gap` banner; toggled **Backup Gaps Only** (`10` rows) → clicked **Export CSV** (zero JS errors) → toggled filter off (`14` rows) | **PASS** |
| **Security** (`/security`) | Verified 3 alerts (`alert_inc_0001`: `83 High`, `alert_inc_0002`: `59 Medium`, `alert_backup_db-prod-orders-01`: `38 Low`) matching Overview 1:1; inspected 5-factor bars (`81`, `100`, `100`, `94`, `0`), AI summary, 3 action steps, and 28 correlated events; clicked **Investigating** → reloaded browser (persisted) → **Resolve** → reloaded browser (persisted) → **Reopen** (restored `open`) | **PASS** |
| **Traffic** (`/traffic`) | Verified `2.4M` 24h requests (`Peak sample: 1.4M requests`), `89%` bot share (`3 flagged endpoints`), `$138` extra bot cost, Recharts chart rendered cleanly, and 3 flagged endpoint verdicts (`/api/catalog/export` `96%`, `/api/pricing/search` `92%`, `/auth/login` `84%`) | **PASS** |
| **Recommendations** (`/recommendations`) | Verified `5 pending, worth $2,190 a month.`; clicked **Approve** on `rec_0001` (`$1,920/mo`) → dropped to `4 pending, worth $270 a month.` → reloaded browser (`Approved` persisted) → **Undo** restored `5`; clicked **Dismiss** → reloaded browser (`Dismissed` persisted) → **Undo** restored `5` | **PASS** |
| **Simulate Incident + Auto-Refresh + Idempotency** | Ran `IAM Breach` in drawer → displayed `68 High` (`Potential IAM Security Breach`), 4 findings, 5 actions, `"Result from the backend simulation."`; closed drawer → Overview automatically updated to `4` active alerts (`0 critical, 2 high`), Security listed `sim_alert_iam_breach` (`High 68`, matching Overview `0 / 2 / 1 / 1`), Recommendations updated `5 -> 7`; ran `IAM Breach` a 2nd time → Recommendations remained **`7`** (idempotent, zero duplicates) | **PASS** |
