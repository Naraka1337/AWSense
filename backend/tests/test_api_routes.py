"""FastAPI TestClient tests for all AWSense API routers backed by SQLite."""

from __future__ import annotations

import sys
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

# Allow running directly from repo root or backend/.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.recommendations import reset_recommendations_state  # noqa: E402
from app.core import database  # noqa: E402
from app.core.database import build_engine, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.entities import (  # noqa: E402
    BackupStatus,
    CloudResource,
    Recommendation,
    RecommendationCategory,
    RecommendationState,
    ResourceType,
)


@pytest.fixture(autouse=True)
def reset_recommendations() -> Generator[None, None, None]:
    """Keep in-memory recommendation state isolated across tests."""

    reset_recommendations_state()
    yield
    reset_recommendations_state()


@pytest.fixture
def client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[TestClient, None, None]:
    """Run the application lifespan against an isolated temporary SQLite DB."""

    db_file = tmp_path / "api_routes_test.db"
    test_engine = build_engine(f"sqlite:///{db_file.as_posix()}")

    test_factory = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_engine,
    )

    # Make the application's lifespan use the temporary database.
    monkeypatch.setattr(database, "engine", test_engine)
    monkeypatch.setattr(database, "SessionLocal", test_factory)

    def override_get_db() -> Generator[Session, None, None]:
        db = test_factory()
        try:
            yield db
        finally:
            db.close()

    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = override_get_db

    try:
        # TestClient starts the lifespan, which creates tables and seeds the DB.
        with TestClient(app) as test_client:
            # Add isolated test data without modifying the team's seed data.
            with test_factory() as session:
                resource = CloudResource(
                    resource_id="test-api-resource",
                    name="API Test Resource",
                    resource_type=ResourceType.EC2,
                    region="us-east-1",
                    status="running",
                    utilization_pct=35.0,
                    backup_status=BackupStatus.PROTECTED,
                    monthly_cost_usd=100.0,
                )

                session.add(resource)
                session.flush()

                recommendation = Recommendation(
                    recommendation_id="test_seed_recommendation",
                    resource_id=resource.resource_id,
                    category=RecommendationCategory.COST,
                    title="Test cost optimization",
                    action="Resize the test EC2 instance",
                    rationale="The test resource can be optimized.",
                    estimated_monthly_savings_usd=50.0,
                    confidence="high",
                    state=RecommendationState.PENDING,
                )

                session.add(recommendation)
                session.commit()

            yield test_client

    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        test_engine.dispose()


def test_base_health_and_openapi_routes(client: TestClient) -> None:
    """Verify baseline endpoints and OpenAPI registration of all API routers."""

    root_resp = client.get("/")
    assert root_resp.status_code == 200
    assert root_resp.json()["status"] == "ok"

    health_resp = client.get("/api/v1/health")
    assert health_resp.status_code == 200
    assert health_resp.json() == {"status": "healthy"}

    openapi_resp = client.get("/openapi.json")
    assert openapi_resp.status_code == 200

    paths = openapi_resp.json()["paths"]
    expected_paths = {
        "/api/v1/overview",
        "/api/v1/resources",
        "/api/v1/alerts",
        "/api/v1/alerts/{alert_id}/status",
        "/api/v1/traffic",
        "/api/v1/recommendations",
        "/api/v1/recommendations/{recommendation_id}/action",
        "/api/v1/simulate",
    }
    assert expected_paths.issubset(set(paths.keys()))


def test_get_overview(client: TestClient) -> None:
    """Verify overview health, savings, alert counts, and trends."""

    resp = client.get("/api/v1/overview")
    assert resp.status_code == 200
    data = resp.json()

    assert 0.0 <= data["health_score"] <= 100.0
    assert data["risk_level"] in {"low", "medium", "high", "critical"}
    assert data["total_monthly_savings_usd"] > 0
    assert data["monthly_spend_usd"] > 0
    assert data["monitored_resources"] >= 14
    assert data["unprotected_resources"] >= 2

    alerts = data["active_alerts"]
    assert alerts["total"] == (
        alerts["critical"] + alerts["high"] + alerts["medium"] + alerts["low"]
    )

    alerts_resp = client.get("/api/v1/alerts")
    assert alerts_resp.status_code == 200
    active_list = [
        item
        for item in alerts_resp.json()["alerts"]
        if item["status"] in {"open", "investigating"}
    ]
    assert alerts["total"] == len(active_list)
    for sev in ("critical", "high", "medium", "low"):
        assert alerts[sev] == sum(1 for item in active_list if item["severity"] == sev)
    if active_list:
        max_score = max(float(item["risk_score"]) for item in active_list)
        assert data["health_score"] == round(max(0.0, min(100.0, 100.0 - max_score)), 1)

    assert len(data["cost_usage_trend"]) >= 5
    first_point = data["cost_usage_trend"][0]
    assert {
        "date",
        "daily_cost_usd",
        "avg_cpu_pct",
        "request_count",
    }.issubset(first_point.keys())


def test_get_resources_and_filters(client: TestClient) -> None:
    """Verify resource inventory and query filters."""

    resp = client.get("/api/v1/resources")
    assert resp.status_code == 200
    data = resp.json()

    assert data["summary"]["total"] == len(data["resources"])
    assert data["summary"]["total"] >= 14

    types = {item["resource_type"] for item in data["resources"]}
    assert {"ec2", "ebs", "rds", "s3"}.issubset(types)

    ec2_resp = client.get(
        "/api/v1/resources",
        params={"resource_type": "ec2"},
    )
    assert ec2_resp.status_code == 200
    ec2_data = ec2_resp.json()
    assert ec2_data["summary"]["total"] >= 1
    assert all(
        item["resource_type"] == "ec2"
        for item in ec2_data["resources"]
    )

    missing_backup_resp = client.get(
        "/api/v1/resources",
        params={"backup_status": "missing"},
    )
    assert missing_backup_resp.status_code == 200
    missing_data = missing_backup_resp.json()

    assert (
        missing_data["summary"]["unprotected_count"]
        == missing_data["summary"]["total"]
    )
    assert all(
        item["backup_status"] == "missing"
        for item in missing_data["resources"]
    )

    region_resp = client.get(
        "/api/v1/resources",
        params={"region": "ap-southeast-1"},
    )
    assert region_resp.status_code == 200
    region_data = region_resp.json()

    assert region_data["summary"]["total"] == 8
    assert all(
        item["region"] == "ap-southeast-1"
        for item in region_data["resources"]
    )


def test_get_alerts_and_filters(client: TestClient) -> None:
    """Verify alerts, ML scores, and severity/status filters."""

    resp = client.get("/api/v1/alerts")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total"] == len(data["alerts"])
    assert data["total"] >= 2

    first_alert = data["alerts"][0]

    assert first_alert["severity"] in {
        "low",
        "medium",
        "high",
        "critical",
    }
    assert 0.0 <= first_alert["risk_score"] <= 100.0
    assert first_alert["ml_score"] is not None
    assert 0.0 <= first_alert["ml_score"] <= 1.0
    assert len(first_alert["correlated_event_ids"]) >= 2
    assert first_alert["summary"]
    assert "iam_risk" in first_alert["signal_breakdown"]
    assert "cost_impact" in first_alert["signal_breakdown"]

    sev_filter = client.get(
        "/api/v1/alerts",
        params={"severity": first_alert["severity"]},
    )
    assert sev_filter.status_code == 200
    sev_data = sev_filter.json()

    assert sev_data["total"] >= 1
    assert all(
        item["severity"] == first_alert["severity"]
        for item in sev_data["alerts"]
    )

    # Filter using an actual status returned by the API.
    alert_status = first_alert["status"]
    status_filter = client.get(
        "/api/v1/alerts",
        params={"status": alert_status},
    )
    assert status_filter.status_code == 200
    status_data = status_filter.json()

    assert status_data["total"] >= 1
    assert all(
        item["status"] == alert_status
        for item in status_data["alerts"]
    )


def test_get_traffic(client: TestClient) -> None:
    """Verify traffic timeline, suspicious endpoints, bot flags, and cost impact."""

    resp = client.get("/api/v1/traffic")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["request_rate_timeline"]) >= 4
    assert any(
        endpoint["bot_flagged"]
        for endpoint in data["suspicious_endpoints"]
    )
    assert data["bot_flags"]["flagged_bot_requests_24h"] > 0
    assert data["bot_flags"]["bot_traffic_pct"] > 0
    assert data["cost_impact"]["estimated_daily_cost_usd"] > 0
    assert data["cost_impact"]["estimated_monthly_cost_usd"] > 0


def test_recommendations_list_and_action_toggle(
    client: TestClient,
) -> None:
    """Verify recommendation listing and DB state transitions."""

    list_resp = client.get("/api/v1/recommendations")
    assert list_resp.status_code == 200
    list_data = list_resp.json()

    assert list_data["total"] >= 4

    categories = {
        item["category"]
        for item in list_data["recommendations"]
    }
    assert {"cost", "security", "backup"}.issubset(categories)

    target_id = "test_seed_recommendation"

    target = next(
        (
            item
            for item in list_data["recommendations"]
            if item["recommendation_id"] == target_id
        ),
        None,
    )
    assert target is not None
    assert target["state"] == "pending"

    # Approve recommendation.
    approve_resp = client.post(
        f"/api/v1/recommendations/{target_id}/action",
        json={"action": "approved"},
    )
    assert approve_resp.status_code == 200

    approve_data = approve_resp.json()
    assert approve_data["previous_state"] == "pending"
    assert approve_data["recommendation"]["state"] == "approved"

    # Confirm state persisted on subsequent GET.
    approved_list = client.get(
        "/api/v1/recommendations",
        params={"state": "approved"},
    ).json()

    assert any(
        item["recommendation_id"] == target_id
        for item in approved_list["recommendations"]
    )

    # Toggle to dismissed.
    dismiss_resp = client.post(
        f"/api/v1/recommendations/{target_id}/action",
        json={"action": "dismissed"},
    )
    assert dismiss_resp.status_code == 200

    dismiss_data = dismiss_resp.json()
    assert dismiss_data["previous_state"] == "approved"
    assert dismiss_data["recommendation"]["state"] == "dismissed"

    # Restore to pending (frontend Undo action).
    undo_resp = client.post(
        f"/api/v1/recommendations/{target_id}/action",
        json={"action": "pending"},
    )
    assert undo_resp.status_code == 200

    undo_data = undo_resp.json()
    assert undo_data["previous_state"] == "dismissed"
    assert undo_data["recommendation"]["state"] == "pending"

    # Unknown ID returns 404.
    missing_resp = client.post(
        "/api/v1/recommendations/rec_does_not_exist/action",
        json={"action": "approved"},
    )
    assert missing_resp.status_code == 404

    # Invalid action payload returns 422.
    invalid_resp = client.post(
        f"/api/v1/recommendations/{target_id}/action",
        json={"action": "delete_everything"},
    )
    assert invalid_resp.status_code == 422


def test_alert_status_transitions_and_validation(client: TestClient) -> None:
    """Verify POST /api/v1/alerts/{alert_id}/status persists transitions and validates input."""
    list_resp = client.get("/api/v1/alerts")
    assert list_resp.status_code == 200
    target_id = list_resp.json()["alerts"][0]["alert_id"]

    # Transition open -> investigating.
    inv_resp = client.post(
        f"/api/v1/alerts/{target_id}/status",
        json={"status": "investigating"},
    )
    assert inv_resp.status_code == 200
    inv_data = inv_resp.json()
    assert inv_data["previous_status"] == "open"
    assert inv_data["alert"]["status"] == "investigating"

    # Transition investigating -> resolved and verify GET filter persistence.
    res_resp = client.post(
        f"/api/v1/alerts/{target_id}/status",
        json={"status": "resolved"},
    )
    assert res_resp.status_code == 200
    assert res_resp.json()["alert"]["status"] == "resolved"

    resolved_list = client.get("/api/v1/alerts", params={"status": "resolved"}).json()
    assert any(item["alert_id"] == target_id for item in resolved_list["alerts"])

    # Transition resolved -> dismissed -> open.
    dis_resp = client.post(
        f"/api/v1/alerts/{target_id}/status",
        json={"status": "dismissed"},
    )
    assert dis_resp.status_code == 200
    assert dis_resp.json()["alert"]["status"] == "dismissed"

    reopen_resp = client.post(
        f"/api/v1/alerts/{target_id}/status",
        json={"status": "open"},
    )
    assert reopen_resp.status_code == 200
    assert reopen_resp.json()["alert"]["status"] == "open"

    # Unknown alert returns 404.
    missing_resp = client.post(
        "/api/v1/alerts/alert_does_not_exist/status",
        json={"status": "resolved"},
    )
    assert missing_resp.status_code == 404

    # Invalid status returns 422.
    invalid_resp = client.post(
        f"/api/v1/alerts/{target_id}/status",
        json={"status": "ignored_invalid"},
    )
    assert invalid_resp.status_code == 422
