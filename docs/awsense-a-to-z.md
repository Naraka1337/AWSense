# AWSense — Complete A-to-Z Project & Codebase Guide

A complete technical and conceptual reference explaining everything AWSense does, why each design choice was made, and how every module from AWS ingestion to the React dashboard works under the hood.

---

## 1. The Big Picture: What AWSense Is & Why It Exists

**AWSense** is an AI-powered cloud security posture management (**CSPM**) and cloud financial operations (**FinOps**) platform for Amazon Web Services (AWS).

### The Problem It Solves
Modern AWS accounts emit massive amounts of monitoring telemetry across separate tools:
1. **Amazon CloudWatch** tracks compute and network utilization (CPU%, bytes in/out, request counts).
2. **AWS CloudTrail & IAM** log who signed in, which permissions changed, and what resources were launched or modified.
3. **Application / ALB / WAF Logs** record incoming HTTP request volume, endpoints hit, IP ranges, and user-agents.
4. **AWS Backup / Snapshots** track whether critical databases and storage volumes can actually be recovered.
5. **AWS Cost Explorer** tracks daily and monthly dollar spend per service.

When reviewed in isolation, these signals miss the real story:
- A CloudWatch alert showing `95% CPU` could look like normal heavy batch work—until you correlate it with an off-hours IAM login from an unseen IP in a new region and a sudden spike in EC2 spend.
- An automated web scraper hitting `/api/catalog/export` 2.4 million times isn't just a traffic anomaly—it drives EC2 CPU past `90%`, triggers scaling, and creates hundreds of dollars in extra data-transfer charges.
- An idle `m5.xlarge` EC2 running at `7%` CPU, an unattached `600 GB` EBS volume, and a production RDS database with backups disabled sit unnoticed draining money and risking catastrophic data loss.

**AWSense connects security events, resource utilization, traffic anomalies, backup hygiene, and cloud billing into one correlated decision-support layer.**

### Why a Standalone Web Dashboard Instead of Native AWS Views?
AWSense runs as an independent React + FastAPI web application rather than embedding widgets inside the native AWS Console because:
- Native CloudWatch/Security Hub views do not easily combine **FinOps cost attribution**, **ML anomaly breakdowns**, **bot-to-bill graphs**, and **plain-English AI remediation checklists** in one unified workflow.
- A decoupled web platform naturally supports multi-account aggregation and offline development/demonstration without live AWS console restrictions.

---

## 2. End-to-End System Architecture

AWSense follows a five-layer architecture running as a unified FastAPI backend + single relational database (SQLite by default for zero setup, PostgreSQL via `DATABASE_URL`) + React Single Page Application (SPA):

```text
  ┌─────────────────────────────────────────────────────────────────────┐
  │ 1. INGESTION LAYER  (telemetry_provider.py, mock_generator.py)      │
  │    DATA_SOURCE=mock ──► MockTelemetryProvider (30d synthetic data)  │
  │    DATA_SOURCE=aws  ──► Boto3TelemetryProvider (EC2/EBS/RDS/S3/     │
  │                         CloudWatch/CloudTrail/Cost Explorer/ALB/WAF)│
  └───────────────────────────────┬─────────────────────────────────────┘
                                  ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │ 2. PERSISTENCE LAYER  (database.py, entities.py, repository.py)     │
  │    SQLAlchemy 2.0 (SQLite / PostgreSQL)                             │
  │    Tables: cloud_resources, telemetry_metrics, security_alerts,     │
  │            recommendations                                          │
  └───────────────────────────────┬─────────────────────────────────────┘
                                  ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │ 3. ANALYTICS, ML & AI LAYER                                         │
  │    • auditor.py       ──► Idle EC2, orphan EBS, backups, bot egress │
  │    • correlator.py    ──► 60-min window multi-signal clustering     │
  │    • ml_detector.py   ──► log1p + StandardScaler + IsolationForest  │
  │    • risk_scorer.py   ──► 5-factor weighted composite risk (0–100)  │
  │    • ai_explainer.py  ──► OpenAI / Gemini / deterministic template  │
  └───────────────────────────────┬─────────────────────────────────────┘
                                  ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │ 4. REST API LAYER  (main.py, api/*.py)                              │
  │    GET  /overview, /resources, /alerts, /traffic, /recommendations  │
  │    POST /alerts/{id}/status, /recommendations/{id}/action, /simulate│
  └───────────────────────────────┬─────────────────────────────────────┘
                                  ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │ 5. PRESENTATION LAYER  (frontend/src/)                              │
  │    VITE_USE_MOCK=true  ──► Local fixtures (frontend/src/mock/)      │
  │    VITE_USE_MOCK=false ──► FastAPI + adapters.js schema mappers     │
  │    Pages: Overview, Resources, Security, Traffic, Recommendations,  │
  │           + SimulatePanel slide-over drawer                         │
  └─────────────────────────────────────────────────────────────────────┘
```

### Dual-Mode Design (Frontend & Backend)
AWSense supports two independent switches:
1. **Frontend switch (`frontend/.env` → `VITE_USE_MOCK`):**
   - `VITE_USE_MOCK=true`: Runs completely standalone in the browser using realistic JS fixtures inside `frontend/src/mock/`. No backend required.
   - `VITE_USE_MOCK=false`: Fetches live JSON from FastAPI (`VITE_API_URL`, proxied cleanly via Vite `/api` in dev) and transforms responses through `frontend/src/services/adapters.js`.
2. **Backend switch (`backend/.env` → `DATA_SOURCE`):**
   - `DATA_SOURCE=mock` (default): Uses `MockTelemetryProvider` to generate repeatable 30-day baselines and compound attack/waste/bot scenarios without spending money or needing AWS credentials.
   - `DATA_SOURCE=aws`: Instantiates `Boto3TelemetryProvider` to pull live read-only data from a real AWS account.

---

## 3. Layer 1: Telemetry Ingestion (`telemetry_provider.py` & `mock_generator.py`)

### The `TelemetryProvider` Interface
Defined in [telemetry_provider.py](file:///g:/Visual%20Studio%20Code%20Folders/AWSense/backend/app/services/telemetry_provider.py), every data source implements 5 standard methods so upstream analytics never care whether data came from real AWS or synthetic generators:
1. `get_resources() -> list[dict]` — EC2, EBS, RDS, and S3 inventory with utilization, backup state, and monthly cost.
2. `get_metrics(resource_id=None, days=30) -> list[dict]` — Time-series CPU, network in/out bytes, and request count.
3. `get_cloudtrail_events() -> list[dict]` — API/IAM audit log records with principal, region, source IP, and anomaly hints.
4. `get_traffic_logs() -> list[dict]` — Endpoint request counts, bot share, user agents, and egress GB.
5. `get_cost_usage(days=30) -> list[dict]` — Daily AWS service spend (`cost_usd`, `baseline_usd`, `delta_usd`, `delta_pct`).

Factory function `get_telemetry_provider(source=None)` reads `DATA_SOURCE` (`"mock"` or `"aws"`).

### How `MockTelemetryProvider` Works ([mock_generator.py](file:///g:/Visual%20Studio%20Code%20Folders/AWSense/backend/app/services/mock_generator.py))
`MockTelemetryGenerator` uses a deterministic random seed (`seed=42` by default) and fixed UTC anchor (`2026-11-21T12:00:00Z`) so tests and demos behave consistently. It supports `include_anomalies=False` (clean 30-day baselines for ML training) and `include_anomalies=True` (full scenarios):

1. **Healthy Baseline Resources:**
   - `i-0baseweb01` (`prod-api-web-01`, EC2 `t3.large`, `us-east-1`, `34.5%` util, protected, `$145.00/mo`)
   - `s3-awsense-audit-logs` (`central-audit-archive`, S3, `us-east-1`, `62.0%` util, protected, `$177.00/mo`)
   - 30-day sinusoidal CPU/network/request curves with slight daily jitter (`120` normal metric rows total across 4 baseline resources).
2. **Scenario 1 — Resource Waste & Backup Gaps:**
   - `i-0a1b2c3d4e5f60001` (`legacy-batch-worker`, EC2 `m5.xlarge`, `7.1%` avg CPU, `$168.00/mo`) — flagged as underutilized.
   - `vol-09911223344556677` (`orphan-analytics-ebs`, EBS `600 GB gp3`, `status="available"`, `attached=False`, `backup_status="missing"`, `$48.00/mo`) — unattached storage waste.
   - `db-prod-orders-01` (`orders-primary-rds`, RDS `db.r6g.large`, `54.3%` CPU, `backup_status="missing"`, `last_backup_at=None`, `$412.25/mo`) — critical resilience gap (`ModifyDBInstance` setting `backupRetentionPeriod: 0`).
3. **Scenario 2 — Compromised IAM + 8 Rogue EC2s (`ap-southeast-1`):**
   - `ct-9001`: Off-hours `ConsoleLogin` (`02:14Z`, no MFA) by `ci-deploy-temp` from `185.220.101.42` in `ap-southeast-1`.
   - `ct-9002`: `AuthorizeSecurityGroupIngress` opening `sg-0f8899aabbccdd` to `0.0.0.0/0` on port `443`.
   - `ct-9003`: `RunInstances` launching 8 `c6i.2xlarge` instances (`i-0rogue0001` through `i-0rogue0008`, `$240.00/mo` each, running at `92%–97.8%` CPU and `85–128 MB` outbound network).
   - `ce-90001`: `AmazonEC2` daily spend jumping `+$420.50` (`+646.9%` over `$65.00` baseline).
4. **Scenario 3 — Automated Scraper / Bot Traffic (`us-east-1`):**
   - `tr-9001` (`/api/catalog/export`, `1,380,000` requests, `96.4%` bot share, `python-requests/2.31.0`)
   - `tr-9002` (`/api/pricing/search`, `745,000` requests, `91.8%` bot share, `Go-http-client/2.0`)
   - `tr-9003` (`/auth/login`, `143,000` POST requests, `84.2%` bot share, `curl/8.5.0`)
   - Pushes `i-0a1b2c3d4e5f60002` (`public-catalog-web`) to `91.4%` CPU, `2,410,000` requests, `354 GB` outbound data, and a `+$138.20` `AWSDataTransfer` cost spike (`ce-00150`).

Can also be executed directly from CLI (`backend/`): `python -m app.services.mock_generator --days 7`.

### How `Boto3TelemetryProvider` Works ([telemetry_provider.py](file:///g:/Visual%20Studio%20Code%20Folders/AWSense/backend/app/services/telemetry_provider.py))
Implements read-only AWS SDK collectors using lazy `boto3.Session` / cached service clients (forcing `us-east-1` for global Cost Explorer `ce`) and wrapping AWS API calls in `try/except (ClientError, BotoCoreError)` with warnings so missing permissions degrade gracefully:
- **Resources (`get_resources`):** Paginates `ec2.describe_instances` (estimates monthly cost by instance type table), `ec2.describe_volumes` (computes cost by GB/volume-type rate and checks `Attachments` & `SnapshotId`), `rds.describe_db_instances` (flags `BackupRetentionPeriod <= 0` as `missing` and `LatestRestorableTime > 7 days` as `outdated`), and `s3.list_buckets`.
- **Metrics (`get_metrics`):** Batches `cloudwatch.get_metric_data` (`CPUUtilization`, `NetworkIn`, `NetworkOut`, max 100 queries per call, hourly if `<=3` days else daily), computes median CPU baseline per instance, and flags `cpu >= 85%` or `>= 2.5x baseline`.
- **CloudTrail (`get_cloudtrail_events`):** Calls `cloudtrail.lookup_events` (up to 5 pages over 24h), parses embedded `CloudTrailEvent` JSON, and flags sensitive calls (`StopLogging`, `DeleteTrail`, `CreateAccessKey`, `RunInstances`, `AuthorizeSecurityGroupIngress`, etc.), off-hours (`<06:00` or `>=22:00 UTC`), or `ConsoleLogin` with `MFAUsed == "No"`.
- **Cost Explorer (`get_cost_usage`):** Calls `ce.get_cost_and_usage` (`DAILY`, `UnblendedCost` grouped by `SERVICE`), compares against per-service median spend, and flags spikes (`delta_usd >= $20` and `>= 50%`, or new service `>= $50`).
- **Traffic (`get_traffic_logs`):** Checks CloudWatch `AWS/ApplicationELB` (`RequestCount`, `ProcessedBytes`) or falls back to `AWS/WAFV2` (`AllowedRequests`, `BlockedRequests`), returning `[]` cleanly when neither exists.
- Verified offline via 7 `botocore.stub.Stubber` unit tests in [test_boto3_provider.py](file:///g:/Visual%20Studio%20Code%20Folders/AWSense/backend/tests/test_boto3_provider.py).

---

## 4. Layer 2: Database, ORM Models & Repository (`database.py`, `entities.py`, `repository.py`)

### Database Engine Configuration ([database.py](file:///g:/Visual%20Studio%20Code%20Folders/AWSense/backend/app/core/database.py))
- Loads `backend/.env` automatically via `python-dotenv`.
- `get_database_url()` reads `DATABASE_URL` or defaults to `sqlite:///<repo>/backend/awsense.db`.
- `build_engine()` adapts automatically:
  - **SQLite:** sets `check_same_thread=False` (for FastAPI request threads) and attaches a SQLAlchemy `"connect"` listener running `PRAGMA foreign_keys=ON` so foreign key constraints and cascades are strictly enforced.
  - **PostgreSQL (or other servers):** enables `pool_pre_ping=True`.
- Exports `Base`, `engine`, `SessionLocal`, `create_tables()`, and the FastAPI dependency generator `get_db()`.

### ORM Schema ([entities.py](file:///g:/Visual%20Studio%20Code%20Folders/AWSense/backend/app/models/entities.py))
All enums inherit from `StrEnum` and store values via `SqlEnum(..., native_enum=False)` alongside portable `JSON` columns so the exact same models run on SQLite and PostgreSQL without DDL migration errors:

1. **`cloud_resources` (`CloudResource`):**
   - `resource_id` (PK), `name`, `resource_type` (`ec2 | ebs | rds | s3`), `region`, `status`, `utilization_pct`, `backup_status` (`protected | missing | outdated | not_applicable`), `last_backup_at`, `monthly_cost_usd`, `metadata_json`, `updated_at`.
   - Relationships: `metrics` (`CASCADE`), `alerts` (no cascade delete), `recommendations` (`CASCADE`).
2. **`telemetry_metrics` (`TelemetryMetric`):**
   - `id` (autoincrement PK), `resource_id` (FK `CASCADE`), `timestamp`, `cpu_utilization`, `network_in_bytes`, `network_out_bytes`, `request_count`, `anomaly_score`.
3. **`security_alerts` (`SecurityAlert`):**
   - `alert_id` (PK), `resource_id` (nullable FK `SET NULL`), `alert_type`, `severity` (`low | medium | high | critical`), `risk_score`, `title`, `correlated_event_ids` (`JSON` list), `signal_breakdown` (`JSON` dict), `ai_summary`, `recommended_actions` (`JSON` list), `status` (`open | investigating | resolved | dismissed`), `created_at`.
4. **`recommendations` (`Recommendation`):**
   - `recommendation_id` (PK), `resource_id` (FK `CASCADE`), `category` (`cost | security | backup`), `title`, `action`, `rationale`, `estimated_monthly_savings_usd`, `confidence`, `state` (`pending | approved | dismissed`), `created_at`, `updated_at`.

### Repository & Startup Seeding ([repository.py](file:///g:/Visual%20Studio%20Code%20Folders/AWSense/backend/app/services/repository.py))
- `seed_database(session, provider=None, force=False)`:
  - Checks if `cloud_resources` already has rows; if so and `force=False`, returns zero counts (idempotent—safe to run on every server restart without duplicating rows).
  - Otherwise ingests from `MockTelemetryProvider` (or given provider), inserts `CloudResource` (`14` rows) and `TelemetryMetric` (`144` rows), runs `correlate_signals()` over anomalous events to create `SecurityAlert` rows (`alert_inc_0001`, `alert_inc_0002`), adds a missing-backup alert for unprotected RDS (`alert_backup_db-prod-orders-01`), and derives `5` actionable `Recommendation` rows (rogue EC2 termination, underutilized EC2 downsizing, orphan EBS deletion, RDS automated backup, WAF bot rate limiting).
- Query & mutation helpers: `list_resources()`, `list_alerts()`, `list_recommendations()`, `update_recommendation_state()`, and `save_alert()` (supports dict, ORM instance, or Pydantic `CorrelatedIncident`, preserving existing fields on partial updates).

---

## 5. Layer 3: Analytics, ML, Correlation & AI Engines

### 5.1 Resource & Traffic Auditor ([auditor.py](file:///g:/Visual%20Studio%20Code%20Folders/AWSense/backend/app/services/auditor.py))
Pure deterministic functions auditing raw resource, metric, and traffic dicts:
- `audit_resources(resources, metrics)`:
  - **Underutilized EC2:** Flags `ec2` with `utilization_pct < 15.0` (falling back to mean CPU from `metrics` if absent), estimating `50%` monthly cost savings.
  - **Unattached EBS:** Flags `ebs` with `status == "available"` and `attached is False`, estimating `100%` monthly cost savings.
  - **Backup Gaps:** Flags any resource with `backup_status` in `{"missing", "outdated"}`.
- `summarize_traffic_impact(traffic_logs)`:
  - Aggregates `total_requests`, `bot_share_pct`, `flagged_endpoints`, and estimates daily/monthly extra egress cost at `$0.09/GB` weighted by `bot_requests / requests` (`EGRESS_COST_PER_GB_USD = 0.09`).

### 5.2 Machine Learning Anomaly Detection ([ml_detector.py](file:///g:/Visual%20Studio%20Code%20Folders/AWSense/backend/app/services/ml_detector.py))
`MLDetector` detects multivariate behavioral anomalies without needing labeled attack data:
- **Input Features:** `[cpu_utilization, network_in_bytes, network_out_bytes, request_count]`.
- **Preprocessing (`_prepare`):** Validates non-null, non-negative numbers, then applies `numpy.log1p(x)` so huge byte/request scales (`10^7`–`10^8`) do not drown out CPU% (`0–100`).
- **Scikit-learn Pipeline:** `StandardScaler()` → `IsolationForest(n_estimators=200, contamination=0.05, random_state=42)`.
- **Fitting (`fit`):** Automatically filters out rows marked `is_anomalous == True` if present, requires at least `10` normal baseline rows, fits the pipeline, and computes calibration statistics from the training `decision_function` distribution (`score_center = 5th percentile`, `score_scale = max(std, 0.05)`).
- **Calibrated Scoring (`predict` / `score_metrics`):**
  Transforms raw `decision_function` score `d` (where lower = more isolated/anomalous) into a `[0.0, 1.0]` probability:
  $$S_{\text{ML}} = \frac{1}{1 + \exp\left(\mathrm{clip}\left(\frac{d - \text{score\_center}}{\text{score\_scale}}, -50, 50\right)\right)}$$
  Points with $S_{\text{ML}} \ge 0.70$ are flagged (`is_anomaly_predicted = True`).

### 5.3 Multi-Signal Temporal Event Correlator ([correlator.py](file:///g:/Visual%20Studio%20Code%20Folders/AWSense/backend/app/services/correlator.py))
`correlate_signals(...)` turns isolated events across CloudTrail, CloudWatch, and Cost Explorer into unified incidents:
1. **Normalization:** Converts `CloudTrailEvent`, `MetricSpike`, and `CostDelta` inputs into UTC-sorted `CorrelatedSignal` objects with `0.0–1.0` severity weights:
   - *CloudTrail:* `risk_hint`, or `0.30` base + `0.35` if `is_anomalous` + `0.25` if in high-risk API set (`ConsoleLogin`, `RunInstances`, `AuthorizeSecurityGroupIngress`, `StopLogging`, `DeleteTrail`, etc.).
   - *MetricSpike:* `anomaly_score`, or scaled relative jump over baseline (`>= 0.75` if CPU/utilization `>= 80%`).
   - *CostDelta:* `0.20 + 0.40 * min(1, delta_usd/500) + 0.40 * min(1, delta_pct/200)`.
2. **Time-Window Clustering (default `time_window_minutes=60`):**
   Signals are scanned chronologically and grouped into open clusters only if the total span stays within 60 minutes, using priority matching:
   - **Priority 1:** Shared `resource_id`.
   - **Priority 2:** CloudTrail signals sharing the same known IAM `principal` in compatible regions.
   - **Priority 3:** Same AWS `region` **only when** either the signal or cluster lacks specific resource IDs (ensuring two distinct EC2 instances in `us-east-1` never falsely merge via a region-only cost event).
   - Clusters with fewer than `min_signals` (`2`) are dropped as isolated noise.
3. **Classification & Breakdown:**
   Labels each cluster as `iam_compute_surge`, `bot_traffic_cost_spike`, `cost_utilization_anomaly`, or `correlated_anomaly`, computes cluster `SignalBreakdown` (`iam_risk`, `resource_impact`, `cost_impact`, `traffic_anomaly`, `total_cost_delta_usd`), and ranks incidents by risk score.

### 5.4 Five-Factor Composite Risk Scorer ([risk_scorer.py](file:///g:/Visual%20Studio%20Code%20Folders/AWSense/backend/app/services/risk_scorer.py))
`score_risk(ml_score, iam_risk, resource_impact, cost_impact, traffic_anomaly)` combines the ML anomaly probability (`0–1`) with the four `0–100` domain factors from `SignalBreakdown`:
$$\text{risk\_score} = 100 \times \left(0.30\cdot\text{ml\_score} + 0.25\cdot\frac{\text{iam\_risk}}{100} + 0.20\cdot\frac{\text{resource\_impact}}{100} + 0.15\cdot\frac{\text{cost\_impact}}{100} + 0.10\cdot\frac{\text{traffic\_anomaly}}{100}\right)$$
Maps the score to severity: `>= 85` → `critical`, `>= 65` → `high`, `>= 40` → `medium`, `< 40` → `low`.

### 5.5 AI Incident Explainer ([ai_explainer.py](file:///g:/Visual%20Studio%20Code%20Folders/AWSense/backend/app/services/ai_explainer.py))
`explain_incident(incident: dict)` turns technical incident payloads into `{ "summary": str, "recommended_actions": ["1. ...", ...] }`:
- **When `OPENAI_API_KEY` or `LLM_API_KEY` is set:** Calls OpenAI Chat Completions (`LLM_MODEL`, default `gpt-4o-mini`) requesting structured JSON (`summary`, `recommended_actions`), treating the incident JSON strictly as evidence.
- **Else if `GEMINI_API_KEY` is set:** Calls Gemini `generateContent` (`GEMINI_MODEL`, default `gemini-3.5-flash-lite`) with `responseMimeType: "application/json"`.
- **When no key is set:** Returns a deterministic template summary (including affected scope, signal count, and USD cost delta) plus 3 standard investigation steps.

### 5.6 ML & Correlation Benchmark ([ml_eval.py](file:///g:/Visual%20Studio%20Code%20Folders/AWSense/backend/app/services/ml_eval.py))
Evaluating `MLDetector(threshold=0.70)` trained on 120 normal rows (`seed=42`, `include_anomalies=False`) against 144 evaluation rows (`seed=43`, `include_anomalies=True`: 119 normal, 25 anomalous) via `python -m app.services.ml_eval` yields:
- **Precision:** `1.0` | **Recall:** `1.0` | **F1:** `1.0` | **False Positive Rate:** `0.0`
- **Confusion Matrix:** `TN = 119`, `FP = 0`, `FN = 0`, `TP = 25`
- **Median Anomaly Score:** `0.1812` (normal) vs. `0.8067` (anomaly) → **+0.6255 score separation**
- **Latency:** `14.94 ms` total (`0.10 ms` per row)

---

## 6. Layer 4: FastAPI REST Backend (`main.py` & `api/*.py`)

### Application Startup ([main.py](file:///g:/Visual%20Studio%20Code%20Folders/AWSense/backend/app/main.py))
- Uses an async `lifespan` context manager (`AsyncGenerator[None, None]`) to call `database.create_tables()` and `seed_database(session)` automatically on server boot.
- Enables CORS (`allow_origins=["*"]` for local dev) and mounts all 6 routers under `/api/v1`.

### Endpoint Reference
| Method & Path | Backing Logic | Behavior |
|---|---|---|
| `GET /` & `GET /api/v1/health` | `main.py` | Basic liveness & health check (`{"status": "healthy"}`). |
| `GET /api/v1/overview` | [overview.py](file:///g:/Visual%20Studio%20Code%20Folders/AWSense/backend/app/api/overview.py) | Queries DB resources, active alerts (`open`/`investigating`), and non-dismissed recommendations to compute `health_score` (`100 - penalties`), `risk_level`, savings, monthly spend, unprotected count, and joins DB `TelemetryMetric` with `MockTelemetryProvider` costs for the 30-day `cost_usage_trend`. |
| `GET /api/v1/resources` | [resources.py](file:///g:/Visual%20Studio%20Code%20Folders/AWSense/backend/app/api/resources.py) | Queries `list_resources(db)` with optional `resource_type`, `region`, and `backup_status` filters; calculates `ResourceSummary` (`total`, `total_monthly_cost_usd`, `unprotected_count`, `underutilized_count`). |
| `GET /api/v1/alerts` | [alerts.py](file:///g:/Visual%20Studio%20Code%20Folders/AWSense/backend/app/api/alerts.py) | Queries `list_alerts(db)` (falling back to `_SAMPLE_ALERTS` only if DB is empty). Runs `score_metrics()` (`IsolationForest`) across stored `TelemetryMetric` rows, resolves `ml_score` directly or via security-group metadata / summary resource IDs, applies `score_risk()` to compute 5-factor `risk_score` and `severity`, fills missing explanations via `explain_incident()`, filters by `severity`/`status`, and sorts descending. |
| `POST /api/v1/alerts/{alert_id}/status` | [alerts.py](file:///g:/Visual%20Studio%20Code%20Folders/AWSense/backend/app/api/alerts.py) | Updates `SecurityAlert.status` (`open \| investigating \| resolved \| dismissed`) in DB; returns `404` if missing, `422` if invalid. |
| `GET /api/v1/traffic` | [traffic.py](file:///g:/Visual%20Studio%20Code%20Folders/AWSense/backend/app/api/traffic.py) | Calls `get_telemetry_provider().get_traffic_logs()` + `summarize_traffic_impact()` (`auditor.py`) + billing `AWSDataTransfer` deltas to build timeline, suspicious endpoints, bot flags, and daily/monthly cost impact. |
| `GET /api/v1/recommendations` | [recommendations.py](file:///g:/Visual%20Studio%20Code%20Folders/AWSense/backend/app/api/recommendations.py) | Queries `list_recommendations(db)` with optional `category` and `state` filters and sums non-dismissed savings. |
| `POST /api/v1/recommendations/{id}/action` | [recommendations.py](file:///g:/Visual%20Studio%20Code%20Folders/AWSense/backend/app/api/recommendations.py) | Persists `pending`, `approved`, or `dismissed` via `update_recommendation_state()` (supporting frontend **Undo**). Returns `404` or `422` on errors. |
| `POST /api/v1/simulate` | [simulate.py](file:///g:/Visual%20Studio%20Code%20Folders/AWSense/backend/app/api/simulate.py) | Accepts `{"scenario": "iam_breach" \| "bot_traffic" \| "resource_waste"}`, runs `MockTelemetryProvider` + `auditor.py` checks, enriches summary/steps via `explain_incident()`, ensures simulated `CloudResource` (`i-sim-*`) exists, upserts `sim_alert_{scenario}`, and inserts simulated `Recommendation` rows into SQLite/PostgreSQL. |

---

## 7. Layer 5: React Frontend & Schema Adapters (`frontend/src/`)

### Tech Stack & Dev Proxy
- **Stack:** React 18.3, Vite 5.4, React Router DOM 6, Tailwind CSS 3.4 (custom dark palette in [tailwind.config.js](file:///g:/Visual%20Studio%20Code%20Folders/AWSense/frontend/tailwind.config.js): `ink: #0E1520`, `panel: #142030`, `raised: #1B2A3E`, `accent: #5AA9FF`, `crit: #F0645A`, `high: #F29A4B`, `med: #E3C453`, `low: #4FBF9F`), Recharts 2, and `lucide-react`.
- **Dev Proxy ([vite.config.js](file:///g:/Visual%20Studio%20Code%20Folders/AWSense/frontend/vite.config.js)):** Automatically proxies `/api/*` to `http://localhost:8000` during `npm run dev` when `VITE_API_URL` points to localhost or is unset.

### How `api.js` and `adapters.js` Connect to the Backend
Backend APIs return wrapped snake_case payloads (`{ resources: [...] }`, `utilization_pct`, `backup_status: "outdated"`, `confidence: "high"`, `bot_traffic_pct: 94.1`), whereas React pages consume clean camelCase shapes:
- **[api.js](file:///g:/Visual%20Studio%20Code%20Folders/AWSense/frontend/src/services/api.js):** Checks `VITE_USE_MOCK`. When `"false"`, fetches `/overview`, `/resources`, `/alerts`, `/traffic`, `/recommendations`, and `POST /recommendations/{id}/action`, piping each response through [adapters.js](file:///g:/Visual%20Studio%20Code%20Folders/AWSense/frontend/src/services/adapters.js):
  - `adaptOverview`: Normalizes uppercase `riskLevel` & `activeAlerts` keys (`CRITICAL/HIGH/MEDIUM/LOW`), formats chart dates, and computes `expected` baseline cost from the series median if omitted.
  - `adaptResources`: Unwraps `resources`, sets `cpu = null` for storage (`ebs`/`s3`), maps `outdated → stale` and `not_applicable → n/a`, formats UTC timestamps, and derives human-readable `finding` messages for waste/backup gaps.
  - `adaptAlerts`: Uppercases severity, builds the 5-factor `breakdown` array (`ml 30%`, `iam 25%`, `resource 20%`, `cost 15%`, `traffic 10%`), infers event sources (`ct*` → `CloudTrail`, `cw*` → `CloudWatch`, `ce*` → `Cost Explorer`, `tr*` → `Traffic logs`), and maps `recommended_actions` → `steps`.
  - `adaptTraffic`: Converts `bot_traffic_pct` (`0–100`) to `botShare` (`0.0–1.0` ratio), distributes daily egress cost proportionally across timeline buckets with cumulative running cost, and merges endpoint patterns.
  - `adaptRecommendations` & `adaptRecommendationAction`: Maps confidence strings (`high→0.9`, `medium→0.7`, `low→0.5`) and unwraps `{ id, state }`.

### Pages & Interactive Components
- **[Layout.jsx](file:///g:/Visual%20Studio%20Code%20Folders/AWSense/frontend/src/components/Layout.jsx) & [ui.jsx](file:///g:/Visual%20Studio%20Code%20Folders/AWSense/frontend/src/components/ui.jsx):** Responsive sidebar + mobile nav, header showing **`Sample data`** vs **`Live data`**, **Refresh** button (remounting `<main key={refreshKey}>`), **Simulate Incident** trigger, and shared `useAsync` / `Async` error-retry boundary.
- **[Overview.jsx](file:///g:/Visual%20Studio%20Code%20Folders/AWSense/frontend/src/pages/Overview.jsx):** 4 KPI cards (Cloud health, Active alerts, Monthly savings, Risk level), 30-day ComposedChart (Area cost vs dashed expected line vs CPU%), and severity progress bars.
- **[Resources.jsx](file:///g:/Visual%20Studio%20Code%20Folders/AWSense/frontend/src/pages/Resources.jsx):** Backup-gap alert banner, text search, type/backup dropdowns, **Backup Gaps Only** toggle, utilization bars, and **Export CSV** (`\uFEFF` UTF-8 BOM + leading-character neutralization against CSV formula injection `= + - @ \t \r`).
- **[Security.jsx](file:///g:/Visual%20Studio%20Code%20Folders/AWSense/frontend/src/pages/Security.jsx):** Split-pane incident feed + detail view showing Risk score, 5-factor breakdown bars, AI incident summary, ordered action steps, and chronological correlated event list.
- **[Traffic.jsx](file:///g:/Visual%20Studio%20Code%20Folders/AWSense/frontend/src/pages/Traffic.jsx):** 24h request volume, bot share %, bot cost impact, ComposedChart (`requests`, `cpu %`, `cost/hr`), and endpoint verdict table.
- **[Recommendations.jsx](file:///g:/Visual%20Studio%20Code%20Folders/AWSense/frontend/src/pages/Recommendations.jsx):** Category badges (`Cost`, `Security`, `Backup`), live pending savings counter, and persistent **Approve** / **Dismiss** / **Undo** buttons.
- **[SimulatePanel.jsx](file:///g:/Visual%20Studio%20Code%20Folders/AWSense/frontend/src/components/SimulatePanel.jsx):** Keyboard-accessible dialog (`Escape` close, `Tab` focus trap, `AbortController` cleanup, `aria-live` updates). Runs local preview when `VITE_USE_MOCK=true` or calls `POST /api/v1/simulate` when `VITE_USE_MOCK=false`, parsing `incident`, `findings`, and `recommendations`.

---

## 8. File Map, Setup Commands & Verified Test Suites

### Repository File Map
- `backend/app/main.py` — FastAPI bootstrap, `lifespan` seeding, CORS, router registration
- `backend/app/core/database.py` — SQLAlchemy engine, `PRAGMA foreign_keys=ON`, `create_tables()`, `get_db()`
- `backend/app/models/entities.py` — 4 ORM models + 6 `StrEnum` definitions
- `backend/app/api/` — `overview.py`, `resources.py`, `alerts.py`, `traffic.py`, `recommendations.py`, `simulate.py`
- `backend/app/services/` — `telemetry_provider.py`, `mock_generator.py`, `repository.py`, `auditor.py`, `correlator.py`, `ml_detector.py`, `risk_scorer.py`, `ai_explainer.py`, `ml_eval.py`
- `backend/tests/` — 10 pytest suites (`55 / 55` passing)
- `frontend/src/` — `App.jsx`, `components/` (`Layout.jsx`, `SimulatePanel.jsx`, `ui.jsx`), `pages/` (5 views), `services/` (`api.js`, `adapters.js`, `adapters.test.mjs`), `mock/` (offline fixtures)
- `docs/` — `awsense-a-to-z.md` (this guide), `system-analysis-and-design.md` (UML/DFD/ERD/methodology), `architecture-and-codebase.md`, `api-contract.json`, `day-*-tasks.md`

### Running Everything Locally
```powershell
# Terminal 1 — Backend (from backend/)
.\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2 — Frontend (from frontend/, with VITE_USE_MOCK=false in frontend/.env for live mode)
npm run dev
```
- Frontend UI: `http://localhost:5173/`
- Backend Swagger Docs: `http://localhost:8000/docs`

### Verified Automated Checks
- **Backend (`55 passed` across 10 files):**
  `backend\.venv\Scripts\python.exe -m pytest backend\tests -v`
  *(Note: In restricted sandboxed terminals that block loopback sockets, `TestClient` suites `test_api_routes.py` and `test_auditor_and_simulate.py` must be run in a regular terminal.)*
- **Frontend Adapters (`6 / 6 passed`):** `node --test frontend/src/services/adapters.test.mjs`
- **Frontend Production Build (`0 errors`):** `npm run build --prefix frontend` (`2,192` modules transformed)
- **ML Benchmark:** `python -m app.services.ml_eval` (from `backend/`)

---

## 9. Exact Current Limitations & Caveats

To keep every technical explanation accurate against the current codebase on `main`:
1. **AWS Live Collectors Verified via `Stubber`:** `Boto3TelemetryProvider` has full read-only collector implementations verified by 7 `botocore.stub.Stubber` unit tests, not yet against a live provisioned AWS sandbox account.
2. **LLM Error Handling in `ai_explainer.py`:** When `OPENAI_API_KEY` or `GEMINI_API_KEY` is unset, `explain_incident()` uses its deterministic template reliably; however, network/HTTP/JSON exceptions when a live API key IS set are not yet caught inside `ai_explainer.py`.
3. **Simulation Scoring & Repeated Runs (`simulate.py`):** Unlike `GET /api/v1/alerts` (which computes `score_risk()`), `POST /api/v1/simulate` currently sets fixed scenario risk scores (`96` / `92` / `78`), generates `sim_<uuid>` recommendations on every call rather than deduplicating, and does not trigger an automatic UI refresh in `Layout.jsx` until the user clicks **Refresh**.
4. **Alert Status UI Controls:** Backend `POST /api/v1/alerts/{alert_id}/status` is implemented and tested, while [Security.jsx](file:///g:/Visual%20Studio%20Code%20Folders/AWSense/frontend/src/pages/Security.jsx) currently displays status read-only (status mutation buttons in the UI exist on Recommendations only).
5. **SQLite Portability Notes:** SQLite strips timezone info on `DateTime(timezone=True)` reads (`alerts.py` normalizes naive datetimes when sorting), and schema changes require recreating local `awsense.db` since Alembic migrations are not configured.
