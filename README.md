# AWSense — Intelligent Cloud Management & Security Platform

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18.3-61DAFB?logo=react&logoColor=black)](https://react.dev)
[![Vite](https://img.shields.io/badge/Vite-5.4-646CFF?logo=vite&logoColor=white)](https://vitejs.dev)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind-3.4-38B2AC?logo=tailwindcss&logoColor=white)](https://tailwindcss.com)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

AWSense is an intelligent cloud management, security posture, and cost optimization platform designed to continuously monitor, correlate, and secure AWS infrastructure.

The platform bridges the gap between Cloud Security Posture Management (**CSPM**) and Cloud Financial Management (**FinOps**). By correlating signals across multiple telemetry sources—such as resource configuration, IAM user activity, network traffic, and billing—AWSense detects anomalies, identifies root causes, calculates an explainable composite risk score, and delivers automated remediation recommendations.

---

## Architecture Overview

AWSense is designed around a decoupled, four-tier architecture:

```
[ AWS APIs / Mock Generator ]
             │
             ▼
[ Ingestion & Normalization Layer ] (boto3 / mock providers)
             │
             ▼
[ Analytics & Intelligence Engine ] (IsolationForest, Correlator, 5-Factor Scorer, AI Explainer)
             │
             ▼
[ Backend REST API & DB Layer ]     (FastAPI, SQLAlchemy ORM, SQLite / PostgreSQL)
             │
             ▼
[ Frontend Presentation Layer ]    (Vite, React 18, Tailwind CSS, Recharts, Schema Adapters)
```

For complete architectural specifications, UML diagrams, entity relationships, and mathematical methodologies, see:
📖 **[docs/system-analysis-and-design.md](docs/system-analysis-and-design.md)**

---

## Core Capabilities

1. **Multi-Signal Correlation Engine (`correlator.py`):** Automatically associates related CloudTrail audit events, CloudWatch metric spikes, and Cost Explorer billing jumps within configurable time windows (60 min) by resource ID, IAM principal, or AWS region.
2. **Machine Learning Anomaly Detection (`ml_detector.py`):** Unsupervised multivariate `IsolationForest` pipeline trained on `cpu_utilization`, `network_in_bytes`, `network_out_bytes`, and `request_count`, with `log1p` logarithmic compression and calibrated sigmoid anomaly scoring (`0.0–1.0`).
3. **Risk Scoring (`correlator.py`, `risk_scorer.py`, `alerts.py`, `overview.py`):** Correlated incidents start with the correlator's cluster score; `GET /api/v1/alerts` and `GET /api/v1/overview` share the same 5-factor `score_risk()` calculation (ML 30%, IAM 25%, resource 20%, cost 15%, traffic 10%) whenever an `IsolationForest` `ml_score` is resolved so alert counts, risk level, and health score stay consistent across pages.
4. **Cloud Hygiene & Cost Auditing (`auditor.py`):** Automatically flags underutilized EC2 instances (<15% CPU), identifies unattached EBS storage volumes, and detects backup gaps (missing or stale recovery points) across RDS and S3.
5. **AI Incident Explanations (`ai_explainer.py`):** Produces a plain-English summary and numbered remediation steps via OpenAI or Gemini when a key is set, falling back cleanly to a deterministic template when no key is configured or on network/HTTP/timeout/malformed-response failures (used by `POST /api/v1/simulate` and as a fallback in `GET /api/v1/alerts`).
6. **Threat Simulation Drawer (`SimulatePanel.jsx`):** On-demand simulation of **IAM Credential Breach**, **Automated Bot Traffic**, and **Resource Waste**, either from local previews (mock mode) or via `POST /api/v1/simulate` (live mode, which calculates 5-factor risk via `score_risk()`, enriches the incident via `explain_incident()`, persists idempotently to DB, and triggers an automatic dashboard refresh).
7. **Interactive Dashboard & Sanitized CSV Export:** Client-side sorting, "Backup Gaps Only" toggle, alert lifecycle status endpoint & UI controls (`POST /api/v1/alerts/{id}/status`), dynamic KPI metrics, and formula-injection-safe CSV export (`\uFEFF` UTF-8 BOM, `= + - @ \t \r` prefix protection).

---

## Live Repository Structure

```
AWSense/
├── backend/
│   ├── app/
│   │   ├── api/                  # FastAPI routers
│   │   │   ├── alerts.py         # /api/v1/alerts & /api/v1/alerts/{id}/status endpoints
│   │   │   ├── overview.py       # /api/v1/overview KPIs & historical trends
│   │   │   ├── recommendations.py# /api/v1/recommendations & action approval
│   │   │   ├── resources.py      # /api/v1/resources & inventory filtering
│   │   │   ├── simulate.py       # /api/v1/simulate persistent scenario engine
│   │   │   └── traffic.py        # /api/v1/traffic analytics & endpoint patterns
│   │   ├── core/
│   │   │   └── database.py       # SQLAlchemy engine, session factory, pragmas
│   │   ├── models/
│   │   │   └── entities.py       # ORM entities (CloudResource, TelemetryMetric, etc.)
│   │   ├── services/
│   │   │   ├── ai_explainer.py   # LLM incident synthesis (OpenAI/Gemini/fallback)
│   │   │   ├── auditor.py        # Resource rightsizing and egress attribution
│   │   │   ├── correlator.py     # Pure-Python time-window correlation engine
│   │   │   ├── ml_detector.py    # IsolationForest anomaly detector pipeline
│   │   │   ├── ml_eval.py        # ML precision/recall/F1 & latency benchmark
│   │   │   ├── mock_generator.py # Deterministic synthetic AWS telemetry fixtures
│   │   │   ├── repository.py     # Database CRUD and idempotent seeder
│   │   │   ├── risk_scorer.py    # 5-factor composite mathematical scoring formula
│   │   │   └── telemetry_provider.py # Provider abstraction (Mock & Boto3 collectors)
│   │   └── main.py               # FastAPI application startup, CORS, and routers
│   ├── tests/                    # Pytest unit, API & smoke suites (71 tests, 10 modules)
│   ├── requirements.txt          # Python dependencies
│   ├── pytest.ini                # Pytest configuration
│   └── .env.example              # Backend environment template
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Layout.jsx        # Navigation shell, header, Refresh & Simulate buttons
│   │   │   ├── SimulatePanel.jsx # Self-contained accessible incident simulation drawer
│   │   │   └── ui.jsx            # Design system tokens, Card, Pill, SeverityBadge
│   │   ├── pages/
│   │   │   ├── Overview.jsx      # High-level KPIs, health score, cost trend chart
│   │   │   ├── Recommendations.jsx # Optimization playbooks & approval workflow
│   │   │   ├── Resources.jsx     # Inventory table, Backup Gaps toggle, CSV export
│   │   │   ├── Security.jsx      # Correlated alert feed, breakdown bars, action steps
│   │   │   └── Traffic.jsx       # Egress trends, bot share %, endpoint patterns
│   │   ├── services/
│   │   │   ├── adapters.js       # Backend-to-UI schema mapper functions
│   │   │   ├── adapters.test.mjs # Unit tests for frontend adapters
│   │   │   └── api.js            # Unified API service with mock/live toggling
│   │   ├── App.jsx               # React Router configuration
│   │   └── main.jsx              # React application entrypoint
│   ├── package.json              # Node.js dependencies and scripts
│   ├── tailwind.config.js        # Design system palette (ink, panel, raised, crit...)
│   ├── vite.config.js            # Vite build configuration
│   └── .env.example              # Frontend environment template
└── docs/
    ├── system-analysis-and-design.md # Full engineering analysis & Mermaid diagrams
    ├── architecture-and-codebase.md  # Deep-dive codebase technical reference
    ├── awsense-a-to-z.md             # A-to-Z project & codebase walkthrough
    ├── verification-report.md        # Live 2-server QA & browser verification report
    └── api-contract.json             # REST API payload contracts
```

---

## Local Setup & Quick Start Runbook

### Prerequisites
- **Python:** 3.11 or newer (the code imports `enum.StrEnum`; tested on 3.12)
- **Node.js:** 18.x or newer (tested on 22)
- **Package Managers:** `pip` and `npm` (v9+)

---

### 1. Backend Setup & Runbook

#### Step 1: Create and Activate Virtual Environment
Open a terminal in the project root:

```bash
# Navigate to the backend directory
cd backend

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Windows (CMD):
.venv\Scripts\activate.bat
# Linux / macOS:
source .venv/bin/activate
```

#### Step 2: Install Dependencies
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

#### Step 3: Configure Environment Variables
Create a local `.env` file from the template:

```bash
cp .env.example .env
```

Contents of `backend/.env`:
```env
# Database connection string (defaults to backend/awsense.db when unset)
DATABASE_URL=sqlite:///./awsense.db

# Enable SQL statement logging (true | false)
SQL_ECHO=false
```

Optional runtime environment variables supported by the backend:

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `DATA_SOURCE` | `mock` | `mock` or `aws` (`Boto3TelemetryProvider` implements read-only EC2/EBS/RDS/S3/CloudWatch/CloudTrail/Cost Explorer collectors) |
| `OPENAI_API_KEY` / `LLM_API_KEY` | unset | Enables OpenAI explanations; `LLM_MODEL` defaults to `gpt-4o-mini` |
| `GEMINI_API_KEY` | unset | Enables Gemini explanations (used only if no OpenAI key); `GEMINI_MODEL` overrides the model |
| `AWS_REGION`, `AWS_PROFILE` | `us-east-1`, unset | Used by `Boto3TelemetryProvider` |
| `CORS_ORIGINS` | `*` | Comma-separated allowed CORS origins for FastAPI (defaults to `*` for local development) |

`.env` is loaded from the `backend/` directory regardless of where you start uvicorn.

#### Step 4: Database Initialization
AWSense initializes and seeds the database automatically on startup via the FastAPI lifespan hook (`app/main.py`), using `get_telemetry_provider()` (`DATA_SOURCE=mock` by default).

To manually initialize and seed the database ahead of time:
```bash
python -c "from app.core import database; from app.services.repository import seed_database; database.create_tables(); s = database.SessionLocal(); seed_database(s); s.close(); print('Database initialized and seeded.')"
```

#### Step 5: Run the Backend Test Suite & ML Benchmark
Verify that all 71 unit and integration tests pass:
```bash
pytest -v
# or, from the repository root:
pytest backend/tests -v
```
Run the ML detection and correlation benchmark:
```bash
python -m app.services.ml_eval
```

#### Step 6: Start the FastAPI Backend Server
Run the ASGI server with hot-reload enabled:
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

The server creates the tables and seeds the data on startup. Use `--host 0.0.0.0` only if you need other machines to reach it (configure `CORS_ORIGINS` before production deployment).

- **API Base URL:** `http://localhost:8000`
- **Interactive OpenAPI Docs:** `http://localhost:8000/docs`
- **API Health Check:** `http://localhost:8000/api/v1/health`

| Method | Endpoint |
| :--- | :--- |
| GET | `/api/v1/overview`, `/api/v1/resources`, `/api/v1/alerts`, `/api/v1/traffic`, `/api/v1/recommendations` |
| POST | `/api/v1/alerts/{id}/status` (body `{"status": "open\|investigating\|resolved\|dismissed"}`) |
| POST | `/api/v1/recommendations/{id}/action` (body `{"action": "pending\|approved\|dismissed"}`) |
| POST | `/api/v1/simulate` (body `{"scenario": "iam_breach\|bot_traffic\|resource_waste"}`) |

---

### 2. Frontend Setup & Runbook

#### Step 1: Install Dependencies
Open a second terminal window and navigate to `frontend`:

```bash
cd frontend

# Clean install using package-lock.json
npm ci
# Or standard install:
npm install
```

#### Step 2: Configure Environment Variables
Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Environment options:
- **Sample Data Mode (Offline / Mock):**
  ```env
  VITE_USE_MOCK=true
  VITE_API_URL=http://localhost:8000/api/v1
  ```
  Runs instantly using local fixtures from `src/mock/`. No backend or database required.

- **Live Backend Mode:**
  ```env
  VITE_USE_MOCK=false
  VITE_API_URL=http://localhost:8000/api/v1
  ```
  Connects directly to the FastAPI server and passes responses through `src/services/adapters.js`. Vite reads `.env` at startup, so restart `npm run dev` after changing it. Start the backend first.

#### Step 3: Run Frontend Adapter Tests
```bash
node --test src/services/adapters.test.mjs
```

#### Step 4: Start the Development Server
```bash
npm run dev
```
Open your browser to: **`http://localhost:5173/`**

#### Step 5: Build for Production
```bash
npm run build
```
Generates production assets in `frontend/dist/`.

---

## Interactive Features & Verification Runbook

### 1. Incident Simulation Drawer
- Click the **"Simulate Incident"** button (Zap icon) in the top-right header.
- The drawer dialog opens with a dimmed backdrop and full keyboard accessibility (Esc closes, Tab is trapped).
- Choose one of three scenarios:
  - **IAM Breach:** Unfamiliar region login, unauthorized EC2 instances launched, security group opened to `0.0.0.0/0`.
  - **Bot Traffic:** 96x HTTP request flood on `/api/products` driving CPU utilization past 85%.
  - **Resource Waste:** Idle worker instances averaging 7% CPU, unattached EBS storage, cold logs in S3.
  - Scores differ by mode: mock mode shows fixed sample previews (`94 critical` / `78 high` / `41 medium`); live mode computes the 5-factor `score_risk()` score from mock telemetry (`68 high` / `51 medium` / `54 medium`).
- Click **"Run simulation"**:
  - In mock mode (`VITE_USE_MOCK=true`): Renders instant local preview.
  - In live mode (`VITE_USE_MOCK=false`): Dispatches `POST /api/v1/simulate` to the FastAPI backend, which evaluates the scenario via `score_risk()`, enriches the explanation via `explain_incident()`, persists the simulated resource, alert (`signal_breakdown` + `correlated_event_ids`), and idempotent `sim_*` recommendations to the database, and triggers an automatic dashboard refresh.

### 2. Resource Inventory & CSV Export (`/resources`)
- **Resource Inventory:** Displays all tracked compute, storage, and database resources with CPU utilization gauges and backup badges.
- **Backup Gaps Only Toggle:** Click **"Backup Gaps Only"** (`ShieldAlert` icon) to instantly isolate resources whose backup is `missing` or stale/`outdated` (the API value is `outdated`; the UI shows `stale`).
- **Export CSV Button:** Click **"Export CSV"** (`Download` icon) to export the filtered rows to `awsense-resources-YYYY-MM-DD.csv`. The output includes a UTF-8 BOM, quotes special characters, and sanitizes spreadsheet formula injection.
- **Refresh Control:** Click **"Refresh"** (`RefreshCw` icon) in the header to re-fetch and remount active view data cleanly.

---

## Testing & Quality Assurance Summary

| Test Command | Scope | Target | Result |
| :--- | :--- | :--- | :---: |
| `pytest backend/tests -v` | Backend Unit & Integration Tests (10 modules) | Database, ORM, ML, ML Eval, Boto3 Stubber, Correlator, Auditor, API, Simulate, Repository, Smoke | **71 / 71 PASSED** |
| `node --test frontend/src/services/adapters.test.mjs` | Frontend Adapter Tests | Overview, Resources, Alerts, Traffic, Recommendations schema mappers | **6 / 6 PASSED** |
| `npm run build --prefix frontend` | Production Bundle Compilation | Vite React compilation, PostCSS, Tailwind CSS | **PASSED (0 errors)** |

---

## License

This project is licensed under the MIT License.
