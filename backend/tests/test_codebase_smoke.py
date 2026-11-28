"""General codebase smoke test verifying backend modules, routes, DB pipeline, and frontend fixtures."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.alerts import get_alerts  # noqa: E402
from app.api.overview import get_overview  # noqa: E402
from app.api.recommendations import (  # noqa: E402
    RecommendationActionRequest,
    act_on_recommendation,
    get_recommendations,
)
from app.api.resources import get_resources  # noqa: E402
from app.api.simulate import SimulationRequest, simulate_scenario  # noqa: E402
from app.api.traffic import get_traffic  # noqa: E402
from app.core.database import build_engine, create_tables  # noqa: E402
from app.main import app, health_check, read_root  # noqa: E402
from app.models.entities import BackupStatus, RecommendationState  # noqa: E402
from app.services.ml_eval import evaluate_ml  # noqa: E402
from app.services.mock_generator import MockTelemetryProvider  # noqa: E402
from app.services.telemetry_provider import (  # noqa: E402
    Boto3TelemetryProvider,
    get_telemetry_provider,
)
from app.services.repository import (  # noqa: E402
    list_alerts,
    list_recommendations,
    list_resources,
    seed_database,
    update_recommendation_state,
)


def test_fastapi_routes_and_handlers_smoke(tmp_path: Path) -> None:
    """Verify all expected API paths are registered and DB-backed handlers return valid payloads."""
    openapi_paths = set(app.openapi()["paths"].keys())
    expected_paths = {
        "/",
        "/api/v1/health",
        "/api/v1/overview",
        "/api/v1/resources",
        "/api/v1/alerts",
        "/api/v1/alerts/{alert_id}/status",
        "/api/v1/traffic",
        "/api/v1/recommendations",
        "/api/v1/recommendations/{recommendation_id}/action",
        "/api/v1/simulate",
    }
    assert expected_paths.issubset(openapi_paths)

    assert read_root()["status"] == "ok"
    assert health_check() == {"status": "healthy"}

    db_file = tmp_path / "handlers_smoke.db"
    engine = build_engine(f"sqlite:///{db_file.as_posix()}")
    create_tables(engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    with session_factory() as session:
        seed_database(session)

        overview = get_overview(db=session)
        assert 0.0 <= overview.health_score <= 100.0
        assert overview.active_alerts.total >= 1

        resources = get_resources(resource_type=None, region=None, backup_status=None, db=session)
        assert resources.summary.total == len(resources.resources) >= 14

        alerts = get_alerts(severity=None, status=None, db=session)
        assert alerts.total == len(alerts.alerts) >= 2

        traffic = get_traffic()
        assert traffic.bot_flags.flagged_bot_requests_24h > 0

        recs = get_recommendations(category=None, state=None, db=session)
        assert recs.total >= 4
        first_id = recs.recommendations[0].recommendation_id
        toggled = act_on_recommendation(
            first_id,
            RecommendationActionRequest(action="approved"),
            db=session,
        )
        assert toggled.recommendation.state == RecommendationState.APPROVED
        restored = act_on_recommendation(
            first_id,
            RecommendationActionRequest(action="pending"),
            db=session,
        )
        assert restored.recommendation.state == RecommendationState.PENDING

    engine.dispose()


def test_end_to_end_provider_correlator_and_db_pipeline(tmp_path: Path) -> None:
    """Verify MockTelemetryProvider -> correlator -> ORM seed -> repository queries end-to-end."""
    db_file = tmp_path / "smoke.db"
    engine = build_engine(f"sqlite:///{db_file.as_posix()}")
    create_tables(engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    provider = MockTelemetryProvider(seed=42, include_anomalies=True)
    with session_factory() as session:
        counts = seed_database(session, provider=provider)
        assert counts["resources"] >= 14
        assert counts["metrics"] >= 100
        assert counts["alerts"] >= 2
        assert counts["recommendations"] >= 4

        missing_backups = list_resources(session, backup_status=BackupStatus.MISSING)
        assert any(r.resource_id == "db-prod-orders-01" for r in missing_backups)

        alerts = list_alerts(session)
        assert any(a.alert_type == "iam_compute_surge" for a in alerts)
        assert any(a.alert_type == "bot_traffic_cost_spike" for a in alerts)

        recs = list_recommendations(session)
        updated = update_recommendation_state(session, recs[0].recommendation_id, "approved")
        assert updated.state == RecommendationState.APPROVED

    engine.dispose()


def test_frontend_structure_and_mock_fixtures_smoke() -> None:
    """Verify required frontend files exist and mock ES module fixtures load cleanly in Node."""
    frontend_dir = REPO_ROOT / "frontend"
    required_files = [
        "package.json",
        "index.html",
        "src/App.jsx",
        "src/components/Layout.jsx",
        "src/components/SimulatePanel.jsx",
        "src/components/ui.jsx",
        "src/pages/Overview.jsx",
        "src/pages/Resources.jsx",
        "src/pages/Security.jsx",
        "src/pages/Traffic.jsx",
        "src/pages/Recommendations.jsx",
        "src/services/api.js",
        "src/mock/index.js",
    ]
    for rel_path in required_files:
        assert (frontend_dir / rel_path).is_file(), f"Missing frontend file: {rel_path}"

    node_bin = shutil.which("node")
    if node_bin is None:
        pytest.skip("Node.js not available in PATH for ES module fixture verification")

    mock_index_uri = (frontend_dir / "src" / "mock" / "index.js").as_uri()
    script = (
        f"import * as m from '{mock_index_uri}'; "
        "console.log(JSON.stringify({"
        "healthScore: m.overview.healthScore, "
        "resources: m.resources.length, "
        "alerts: m.alerts.length, "
        "trafficTotal: m.traffic.totalRequests, "
        "recommendations: m.recommendations.length"
        "}));"
    )
    proc = subprocess.run(
        [node_bin, "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        check=True,
    )
    summary = json.loads(proc.stdout)
    assert 0 <= summary["healthScore"] <= 100
    assert summary["resources"] >= 5
    assert summary["alerts"] >= 2
    assert summary["trafficTotal"] > 0
    assert summary["recommendations"] >= 4


def test_ml_eval_and_aws_provider_smoke() -> None:
    """Verify ML evaluation benchmark and AWS Boto3TelemetryProvider factory resolution."""
    report = evaluate_ml()
    assert report["precision"] >= 0.95
    assert report["recall"] >= 0.95
    assert report["f1"] >= 0.95
    assert report["score_separation"] > 0
    assert report["confusion_matrix"]["tp"] > 0
    assert report["inference_ms_total"] > 0
    assert len(report["incidents"]) >= 1

    aws_provider = get_telemetry_provider("aws")
    assert isinstance(aws_provider, Boto3TelemetryProvider)
    assert aws_provider.source_name == "aws"
    for method_name in (
        "get_resources",
        "get_metrics",
        "get_cloudtrail_events",
        "get_traffic_logs",
        "get_cost_usage",
    ):
        assert callable(getattr(aws_provider, method_name))

    with pytest.raises(ValueError, match="Unsupported DATA_SOURCE"):
        get_telemetry_provider("invalid_source")


def test_simulate_panel_contract_smoke(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify POST /api/v1/simulate handler output matches SimulatePanel.jsx expectations."""
    for key in ("LLM_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    db_file = tmp_path / "simulate_smoke.db"
    engine = build_engine(f"sqlite:///{db_file.as_posix()}")
    create_tables(engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    try:
        with session_factory() as session:
            for scenario in ("iam_breach", "bot_traffic", "resource_waste"):
                result = simulate_scenario(
                    SimulationRequest(scenario=scenario),
                    db=session,
                )
                payload = result.model_dump(mode="json")

                assert set(payload.keys()) == {"incident", "findings", "recommendations"}
                incident = payload["incident"]
                assert isinstance(incident["title"], str) and incident["title"]
                assert isinstance(incident["risk_score"], int)
                assert 0 <= incident["risk_score"] <= 100
                assert incident["severity"] in {"critical", "high", "medium", "low"}
                assert isinstance(incident["summary"], str) and incident["summary"]
                assert isinstance(incident["recommended_actions"], list)
                assert len(incident["recommended_actions"]) >= 1
                assert isinstance(payload["findings"], list) and len(payload["findings"]) >= 1
                assert isinstance(payload["recommendations"], list)
                assert len(payload["recommendations"]) >= 1
                assert all(
                    isinstance(rec, dict) and (rec.get("action") or rec.get("title"))
                    for rec in payload["recommendations"]
                )
    finally:
        engine.dispose()

