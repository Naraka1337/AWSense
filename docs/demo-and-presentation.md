# AWSense — Live Demo & Presentation Runbook

A practical guide for presenting **AWSense** in a 5–7 minute academic or technical defense, running the live two-server demonstration, falling back safely offline if needed, and answering technical Q&A questions.

---

## 1. 5–7 Minute Slide Outline (Aligned to Grading Criteria)

| Time | Slide | Focus & Key Visuals | Rubric Alignment |
|---|---|---|---|
| `0:00 – 0:45` | **1. Problem & Motivation** | Siloed AWS telemetry (CloudWatch, CloudTrail, ALB/WAF, Backups, Cost Explorer) misses cross-domain attacks, scraper cost spikes, and unmonitored waste. | Problem Definition & Impact |
| `0:45 – 1:45` | **2. System Architecture** | 5-layer diagram (`TelemetryProvider` → SQLAlchemy DB → Analytics/ML/AI → FastAPI → React SPA) + Dual-Mode switches (`DATA_SOURCE=mock\|aws`, `VITE_USE_MOCK=true\|false`). | System Design & Modularity |
| `1:45 – 3:00` | **3. Analytics, ML & Risk Engine** | `log1p` + `StandardScaler` + `IsolationForest` pipeline; 60-min temporal correlator (Resource → Principal → Region guard); 5-factor formula (`30% ML + 25% IAM + 20% Resource + 15% Cost + 10% Traffic`); OpenAI/Gemini + deterministic fallback. | Algorithms, ML & Engineering Depth |
| `3:00 – 5:30` | **4. Live System Demo** | Walkthrough across Overview, Resources (`Backup Gaps Only` + CSV), Security (5-factor breakdown & status triage), Traffic, Recommendations (`Approve`/`Undo`), and `Simulate Incident` drawer. | Implementation & UX Quality |
| `5:30 – 6:15` | **5. Verification & Benchmarks** | **73 / 73** backend pytest pass (incl. 7 `Stubber` AWS tests), **6 / 6** adapter tests, Vite build (`2,192` modules), synthetic ML benchmark (`1.0` precision/recall/F1, `+0.6255` score separation). | Testing, QA & Scientific Rigor |
| `6:15 – 7:00` | **6. Scope Limits & Future Work** | Honest caveats (`Stubber` vs. real AWS sandbox, Alembic migrations, `CORS_ORIGINS`/auth) and next roadmap steps. | Critical Reflection |

---

## 2. Live Two-Server Setup & Pre-Demo Check

Run in **two terminals** from the repository root (`AWSense/`) 5 minutes before presenting:

```powershell
# Terminal 1 — FastAPI Backend (creates/seeds SQLite awsense.db automatically)
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

```powershell
# Terminal 2 — React Frontend in Live Mode
$env:VITE_USE_MOCK = "false"
$env:VITE_API_URL = "http://localhost:8000/api/v1"
npm.cmd run dev --prefix frontend -- --port 5173
```

Open **`http://localhost:5173/`** in Chrome and confirm:
- Top bar shows **`Live data`** pill and **`us-east-1 and ap-southeast-1`**.
- Open **`http://localhost:8000/docs`** in a second tab if evaluators want to inspect the OpenAPI Swagger schema.

---

## 3. Exact Live Demo Click-Through Sequence (~2.5 min)

1. **Overview (`/`):**
   - Point out **Cloud health (`17/100`)**, **Active alerts (`3`)**, **Monthly savings available (`$2,190`)**, and **Risk level (`High`)**.
   - Hover over the **30-day cost & CPU trend** spike where anomalous bot + EC2 activity deviates from baseline spend.
2. **Resources (`/resources`):**
   - Highlight the **10 backup gaps** alert banner above the 14-resource table.
   - Click **Backup Gaps Only** to filter down to unprotected EBS/RDS/rogue EC2 resources, then click **Export CSV** (note UTF-8 BOM + CSV formula-injection escaping).
3. **Security (`/security`):**
   - Select the top correlated IAM alert (`alert_inc_0001`, score **`83` High**) and explain how CloudTrail + CloudWatch + Cost Explorer signals correlated cleanly, with the 5-factor bars and numbered AI remediation steps.
   - Click **Investigating** and refresh the page to prove status updates persist in SQLite (`POST /api/v1/alerts/{id}/status`), then click **Reopen**.
4. **Traffic (`/traffic`):**
   - Show **`2.4M` requests**, **`89%` bot share**, **`$138` bot cost impact**, and the flagged endpoint table (`python-requests`, `Go-http-client`, `curl`).
5. **Recommendations (`/recommendations`):**
   - Click **Approve** on one recommendation (showing the pending monthly savings tally recalculate live), then click **Undo** to restore `"pending"` cleanly.
6. **Simulate Incident Drawer (Header button):**
   - Click **Simulate Incident**, select **IAM Breach**, and click **Run simulation**.
   - Show the live result (**`68` High**, findings, numbered AI actions), close the drawer, and show **`Security`** / **`Overview`** auto-refreshed automatically (`onSimulated`) without manual reload.

---

## 4. Instant Offline Fallback Steps

Use these immediately if Wi-Fi, port `8000`, or an external LLM key fails during the presentation:

1. **No Backend / Port Conflict Fallback (`VITE_USE_MOCK=true`):**
   ```powershell
   $env:VITE_USE_MOCK = "true"
   npm.cmd run dev --prefix frontend -- --port 5173
   ```
   The header switches to **`Sample data`** (`us-east-1 and eu-west-1`), and all 5 pages + `SimulatePanel` run standalone from `frontend/src/mock/`.
2. **LLM Key Missing or Network Error (`ai_explainer.py`):**
   Do nothing — when `OPENAI_API_KEY`/`GEMINI_API_KEY` is unset or an upstream HTTP/JSON error occurs, `explain_incident()` logs a sanitized warning and automatically returns its deterministic summary and 3 numbered remediation steps (never crashing with HTTP 500).
3. **Fresh Reset of Demo DB:**
   Stop uvicorn, delete `backend/awsense.db`, and restart uvicorn to re-seed cleanly to initial state.

---

## 5. High-Frequency Q&A Defense Notes

- **Why unsupervised `IsolationForest` instead of supervised classification?** Real accounts rarely have labeled multi-stage attacks in advance; `IsolationForest` baselines normal utilization curves (`cpu_utilization`, `network_in_bytes`, `network_out_bytes`, `request_count`) and scores unseen multi-metric anomalies cleanly.
- **Why `log1p` before `StandardScaler`?** Raw byte counts (`10^8`) and request counts (`2.4M`) span orders of magnitude compared to CPU (`0–100%`). `np.log1p()` prevents large-scale counts from dominating z-scores.
- **How does `correlator.py` avoid false merges?** Strict 3-tier matching over a 60-minute window: (1) shared `resource_id`, (2) shared known IAM `principal`, (3) same `region` *only* when at least one signal has no pinned `resource_id` (e.g., regional Cost Explorer spend deltas).
- **Why keep `Overview` and `Security` aligned via `score_alerts()`?** Startup seeding persists the initial cluster score (`100.0`), while live ML metric scoring refines severity on read; sharing `score_alerts()` prevents Overview KPIs from ever disagreeing with the Security page.
- **Is live AWS telemetry implemented?** Yes — `Boto3TelemetryProvider` implements read-only EC2, EBS, RDS, S3, CloudWatch, CloudTrail, Cost Explorer, and ALB/WAFv2 collectors verified via 7 `botocore.stub.Stubber` tests; live cloud execution only needs AWS credentials (`DATA_SOURCE=aws`).
- **Why human-in-the-loop approvals instead of auto-termination?** Automatically deleting EBS volumes or terminating EC2 instances risks outage or data loss before backups are verified; AWSense surfaces savings and waits for explicit `Approve` / `Dismiss` decisions.
