# AWSense — Architecture & Codebase Reference

Comprehensive technical guide covering the project vision, current codebase implementation, planned modules, data schemas, local setup, and engineering conventions. Written for both human contributors and AI coding agents.

---

## 1. Project Purpose & Core Problem

**AWSense** is an AI-assisted AWS cloud security posture (CSPM) and cost optimization (FinOps) platform delivered as a standalone web application.

### The Core Problem
AWS environments emit telemetry across disconnected services:
- **CloudWatch** reports compute/network metrics (e.g., CPU spikes).
- **CloudTrail / IAM** logs API calls, logins, and configuration changes.
- **Traffic / ALB / WAF logs** record request volume and endpoint patterns.
- **AWS Backup / Snapshots** track resource protection status.
- **Cost Explorer** reports daily and monthly spend.

Analyzed separately, isolated alerts produce noise. Correlated together, they expose high-value incidents—such as compromised IAM credentials spinning up compute instances in an unused region, or automated scraper bots inflating EC2 CPU and bandwidth bills.

### Core Objectives
1. Detect underutilized EC2 instances, unattached EBS volumes, and unprotected resources missing recent backups.
2. Baseline IAM principal and resource behavior, scoring deviations with unsupervised ML (`IsolationForest`).
3. Detect automated/bot traffic impacts on compute utilization and cloud spend.
4. Correlate security, utilization, traffic, and cost signals into unified incidents with an overall risk score.
5. Generate human-readable AI incident explanations and remediation actions with human-in-the-loop approval (`pending` / `approved` / `dismissed`).

---

## 2. Implementation Status Snapshot

The project has progressed from the initial database and API scaffold to a functional MVP with telemetry providers, resource auditing, ML anomaly detection, risk scoring, AI explanations, simulation persistence, and dashboard API endpoints.

| Area | Status | Notes |
|---|---|---|
| Repository layout & documentation (`README.md`, `docs/*`) | **Implemented** | Architecture reference, task distribution, API contract, and implementation documentation |
| Python environment & tooling | **Implemented** | FastAPI, SQLAlchemy, pytest, and backend configuration |
| Database connection & ORM schema | **Implemented & Tested** | SQLite by default, PostgreSQL-compatible SQLAlchemy models, and four core tables |
| FastAPI bootstrap (`app/main.py`) | **Implemented** | Application setup, CORS, database initialization, and domain router registration |
| Telemetry providers | **Implemented** | Mock telemetry provider and Boto3-based AWS telemetry collectors |
| Resource & backup auditing (`auditor.py`) | **Implemented & Tested** | Detects underutilized EC2, unattached EBS, and missing or outdated backups |
| ML anomaly detection (`ml_detector.py`) | **Implemented** | IsolationForest-based anomaly detection |
| Unified risk scoring (`risk_scorer.py`) | **Implemented** | Weighted scoring using ML, IAM, resource, cost, and traffic factors |
| AI incident explanations (`ai_explainer.py`) | **Implemented** | AI-generated explanations and deterministic fallback when an API key is unavailable |
| Event correlation (`correlator.py`) | **Implemented** | Correlates security and telemetry signals into incident context |
| ML evaluation (`ml_eval.py`) | **Implemented** | Evaluation utilities for anomaly detection |
| Repository persistence (`repository.py`) | **Implemented** | Database persistence helpers for resources, alerts, and recommendations |
| Simulation API (`api/simulate.py`) | **Implemented** | IAM breach, bot traffic, and resource waste scenarios with database persistence |
| Dashboard API routers | **Implemented** | Overview, resources, alerts, traffic, and recommendations endpoints |
| Simulation risk breakdown & idempotency | **Implemented** | Five-factor risk scoring, persisted signal breakdown, correlated event IDs, and stable scenario recommendation IDs |
| Frontend dashboard | **Implemented** | React dashboard components including `adapters.js` and `SimulatePanel.jsx` |

---

## 3. System Architecture

AWSense is currently implemented as a **single-process FastAPI application** with a relational database and a telemetry provider abstraction.

The application supports local mock and simulation workflows by default. Boto3-based AWS telemetry collectors are also implemented, but connecting to a live AWS account requires valid credentials, appropriate IAM permissions, and integration testing against the target environment.

The database uses SQLite by default for local development and supports PostgreSQL through the `DATABASE_URL` configuration.

```text
       AWS Environment                         Local Mock Scenarios
  CloudWatch / CloudTrail / IAM          Synthetic Baseline + Injected
  EC2 / EBS / Cost Explorer               Waste, Breach & Bot Events
              │                                      │
              ▼                                      ▼
      Boto3 AWS Collectors                    Mock Telemetry
              │                                      │
              └──────────────────┬───────────────────┘
                                 ▼
                      Normalized Telemetry
                                 │
               ┌─────────────────┼─────────────────┐
               ▼                 ▼                 ▼
         Event Correlator    ML Detector     Resource Auditor
         correlator.py       ml_detector.py    auditor.py
               └─────────────────┼─────────────────┘
                                 ▼
                         Unified Risk Scorer
                          risk_scorer.py
                                 │
                                 ▼
                       AI Incident Explainer
                     LLM API + Fallback Logic
                                 │
                                 ▼
                       SQLAlchemy ORM Layer
                SQLite / PostgreSQL Database
                                 │
                                 ▼
                       FastAPI REST API
                           /api/v1/*
                                 │
                                 ▼
                     React Dashboard
                         frontend/
```

### Key Architectural Choices

- **Standalone Web Application:** AWSense is built as an independent web application, allowing it to present correlated incidents, risk breakdowns, and AI explanations through its own dashboard.
- **Single Relational Database:** SQLAlchemy models store cloud resources, telemetry metrics, security alerts, and recommendations. JSON columns retain structured incident data such as signal breakdowns and correlated event IDs.
- **Telemetry Provider Abstraction:** Telemetry is normalized before being processed by the detection and analysis services. This allows mock data and AWS telemetry collectors to support the same general processing workflow.
- **Unified Risk Scoring:** The risk scorer combines IAM, resource, cost, traffic, and ML signals into a composite incident risk score and severity.
- **AI Explanation Fallback:** Incident explanations use the AI service when configured and deterministic fallback logic when an AI API key is unavailable.
- **Safe Remediation:** Recommendations require human review and support approval or dismissal rather than automatically modifying or terminating cloud infrastructure.

---

## 4. Repository Structure

### Current Files

```text
AWSense/
├── .gitignore
├── LICENSE
├── pyrightconfig.json
├── README.md
├── docs/
│   ├── api-contract.json
│   ├── architecture-and-codebase.md
│   ├── awsense-a-to-z.md
│   ├── day-1-tasks.md
│   ├── day-2-tasks.md
│   ├── day-3-tasks.md
│   ├── day-4-tasks.md
│   ├── day-5-6-tasks.md
│   ├── system-analysis-and-design.md
│   ├── task-distribution.md
│   └── verification-report.md
├── frontend/
│   └── src/
│       ├── services/
│       │   └── adapters.js
│       └── components/
│           └── SimulatePanel.jsx
└── backend/
    ├── .env.example
    ├── pytest.ini
    ├── requirements.txt
    ├── app/
    │   ├── main.py
    │   ├── api/
    │   │   ├── alerts.py
    │   │   ├── overview.py
    │   │   ├── recommendations.py
    │   │   ├── resources.py
    │   │   ├── simulate.py
    │   │   └── traffic.py
    │   ├── core/
    │   │   └── database.py
    │   ├── models/
    │   │   └── entities.py
    │   └── services/
    │       ├── ai_explainer.py
│   │       ├── auditor.py
│   │       ├── correlator.py
│   │       ├── mock_generator.py
│   │       ├── ml_detector.py
│   │       ├── ml_eval.py
│   │       ├── repository.py
│   │       ├── risk_scorer.py
│   │       └── telemetry_provider.py
    └── tests/
        ├── test_api_routes.py
        ├── test_auditor_and_simulate.py
        ├── test_boto3_provider.py
        ├── test_codebase_smoke.py
        ├── test_correlator.py
        ├── test_database.py
        ├── test_ml_ai.py
        ├── test_ml_eval.py
        ├── test_repository.py
        └── test_telemetry_provider.py
```

### Implemented Module Responsibilities

- **`backend/app/api/`** — FastAPI routers for overview, resources, alerts, traffic, recommendations, and simulation.
- **`backend/app/core/database.py`** — SQLAlchemy engine, session management, database configuration, and table creation helpers.
- **`backend/app/models/entities.py`** — ORM models and enums for cloud resources, telemetry metrics, security alerts, and recommendations.
- **`backend/app/services/`** — Telemetry processing, resource auditing, anomaly detection, event correlation, risk scoring, AI explanations, ML evaluation, and persistence helpers.
- **`backend/tests/`** — Database, API route, auditor, and simulation tests.
- **`frontend/src/services/adapters.js`** — Frontend API data adaptation utilities.
- **`frontend/src/components/SimulatePanel.jsx`** — Dashboard simulation interface.

### Future Integration

The application currently supports mock and simulated workflows. Connecting a live AWS environment requires configuring credentials and validating the AWS telemetry provider against the target account and permissions.

### 5.4 Dependencies & Configuration
- `backend/requirements.txt`: Lower-bounded `<next-major` ranges ensuring Python 3.12+ binary wheel installation:
  `fastapi>=0.115.0,<1.0`, `uvicorn>=0.30.0,<1.0`, `pydantic>=2.9.0,<3.0`, `boto3>=1.35.0,<2.0`, `scikit-learn>=1.5.0,<2.0`, `pandas>=2.2.2,<3.0`, `sqlalchemy>=2.0.35,<3.0`, `python-dotenv>=1.0.0,<2.0`, `pytest>=8.0.0,<9.0`, `httpx>=0.27.0,<1.0`.
- `pyrightconfig.json`: Sets `"include": ["backend"]`, `"extraPaths": ["backend"]`, `"venvPath": "backend"`, `"venv": ".venv"` so Pylance/Pyright resolves both third-party packages and `app.*` imports across OSes.
- `backend/pytest.ini`: Sets `pythonpath = .` and `testpaths = tests`.
- `backend/.env.example`: Defaults `DATABASE_URL=sqlite:///./awsense.db`, `SQL_ECHO=false`, with commented PostgreSQL example.

### 5.5 Existing Tests

The backend test suite is located in `backend/tests/` and covers database operations, API routes, resource auditing, simulation behavior, telemetry, event correlation, ML/AI services, and repository persistence.

Implemented test modules include:

- **`test_api_routes.py`** — Tests dashboard API endpoints and FastAPI route behavior.
- **`test_auditor_and_simulate.py`** — Tests resource auditing, simulation scenarios, risk scoring, persisted alert signal breakdowns, and idempotent recommendation persistence.
- **`test_codebase_smoke.py`** — Performs smoke tests to verify core application modules and routes.
- **`test_correlator.py`** — Tests event correlation behavior.
- **`test_database.py`** — Verifies database configuration, table creation, ORM relationships, foreign key behavior, and session lifecycle.
- **`test_ml_ai.py`** — Tests ML anomaly detection and AI explanation services.
- **`test_repository.py`** — Tests database repository operations.
- **`test_telemetry_provider.py`** — Tests telemetry provider behavior and data collection.

Run the complete backend test suite from the repository root:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests -v
```
---

## 6. Implemented Subsystems & Core Scenarios

### Core Detection Scenarios

1. **Resource Waste & Backup Gaps**
   - Detects underutilized EC2 instances and unattached EBS volumes.
   - Identifies resources with missing or outdated backups.
   - Generates cost optimization and backup recommendations.

2. **IAM Breach + Compute Surge**
   - Simulates suspicious IAM activity and related resource or traffic changes.
   - Calculates incident risk using the unified risk scoring service.
   - Persists the resulting incident alert and recommendations.

3. **Automated Bot / Scraper Traffic**
   - Simulates abnormal request patterns and their potential impact on compute utilization and cost.
   - Uses traffic anomaly signals as part of the overall risk assessment.
   - Provides incident context and remediation recommendations.

### Implemented Service Responsibilities

- **Telemetry Ingestion (`telemetry_provider.py`, `mock_generator.py`):** Provides normalized telemetry through mock and AWS-based providers, including Boto3 telemetry collectors.
- **ML Anomaly Detection (`ml_detector.py`):** Uses IsolationForest-based anomaly detection to identify unusual telemetry patterns.
- **Event Correlation (`correlator.py`):** Correlates security and telemetry signals into incident context and associated event IDs.
- **Unified Risk Scoring (`risk_scorer.py`):** Calculates a composite risk score using ML, IAM, resource, cost, and traffic factors, producing a score and severity.
- **AI Explainer (`ai_explainer.py`):** Generates incident explanations and recommended actions, with a deterministic fallback when an AI API key is unavailable.
- **Resource Auditing (`auditor.py`):** Audits resource utilization, unattached volumes, and backup protection gaps.
- **ML Evaluation (`ml_eval.py`):** Provides evaluation utilities for anomaly detection.
- **Repository Persistence (`repository.py`):** Provides database persistence helpers for resources, alerts, and recommendations.
- **Simulation (`api/simulate.py`):** Runs the supported scenarios, calculates risk through the unified risk scorer, and persists simulated resources, alerts, and recommendations.

### Simulation Risk Breakdown & Idempotency

The simulation API uses `score_risk()` rather than hardcoded scenario risk scores.

The persisted alert `signal_breakdown` includes the following factors:

- `iam_risk`
- `resource_impact`
- `cost_impact`
- `traffic_anomaly`
- `ml_score`
- `total_cost_delta_usd`

Alerts also persist `correlated_event_ids` to retain the associated event context.

Simulation alerts use stable scenario-based identifiers. Recommendation persistence is idempotent per simulated scenario and resource: previous simulation recommendations for the same resource are replaced instead of accumulating duplicates when the scenario is repeated.

### Implemented API Endpoints

The FastAPI application exposes dashboard endpoints under `/api/v1`, including:

- `GET /api/v1/overview`
- `GET /api/v1/resources`
- `GET /api/v1/alerts`
- `POST /api/v1/alerts/{alert_id}/status`
- `GET /api/v1/traffic`
- `GET /api/v1/recommendations`
- `POST /api/v1/recommendations/{id}/action`
- `POST /api/v1/simulate`

### Frontend Integration

The dashboard includes React components and API integration utilities, including `src/services/adapters.js` and `SimulatePanel.jsx`, for displaying backend data and running simulation scenarios.

---

## 7. Local Setup & Verification Commands

### Environment Setup (Windows PowerShell)

The backend virtual environment is already created at `backend/.venv`.

To install or update the backend dependencies, run the following command from the repository root:

```powershell
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Optional environment configuration:

```powershell
Copy-Item backend\.env.example backend\.env
```

### Running Tests

Run the resource auditing and simulation tests:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_auditor_and_simulate.py -v
```

Run all backend tests:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests -v
```

### Running the Backend Server

From the repository root, start the FastAPI application:

```powershell
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000 --app-dir backend
```

The interactive API documentation is available at:

`http://localhost:8000/docs`

---

## 8. Design Decisions & Known Caveats

1. **PostgreSQL Driver Not Installed by Default:** `DATABASE_URL` supports PostgreSQL URLs in `build_engine()`, but `psycopg2-binary` (or `psycopg`) is not yet in `backend/requirements.txt`. Add it before connecting to a live PostgreSQL server.

2. **No Schema Migrations (Alembic):** Tables are created through `Base.metadata.create_all()` using `create_tables()`. Modifying columns on existing models requires deleting and recreating the local `awsense.db` database or dropping and recreating the affected tables in PostgreSQL.

3. **Database Initialization:** The FastAPI lifespan handler in `backend/app/main.py` calls `create_tables()` during application startup and initializes the database with seed data using `get_telemetry_provider()` (`DATA_SOURCE=mock` by default).

4. **SQLite Timezone Stripping:** `DateTime(timezone=True)` works across both engines, but SQLite may return naive `datetime` instances when reading records, while PostgreSQL returns timezone-aware instances. Normalize `tzinfo` before comparing timestamps in Python.

5. **FastAPI `TestClient` / `httpx` Warning:** Starlette may log a deprecation warning recommending `httpx2` instead of `httpx` when importing `TestClient`. In restricted Windows environments, `TestClient` may also encounter issues with its internal AnyIO portal socketpair. Run HTTP-level tests in a normal terminal environment if needed.

6. **IDE Analyzer Alignment:** If VS Code or another IDE flags imports after pulling changes or recreating `.venv`, run **Python: Restart Language Server** so it reloads `pyrightconfig.json` and the configured Python environment.
