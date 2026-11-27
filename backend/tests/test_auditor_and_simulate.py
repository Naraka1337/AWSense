
import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.api.simulate import router
from app.core.database import Base, build_engine, get_db
from app.models.entities import CloudResource, Recommendation, SecurityAlert
from app.services.auditor import (
    audit_resources,
    summarize_traffic_impact,
)


# Create a small FastAPI app for testing the simulate router.
app = FastAPI()
app.include_router(router)

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    """Give every test an isolated SQLite database."""
    test_engine = build_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(bind=test_engine)

    TestSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_engine,
    )

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Keep AI explanations deterministic and prevent external API calls.
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")

    yield TestSessionLocal

    app.dependency_overrides.clear()
    test_engine.dispose()


# -------------------------
# Auditor tests
# -------------------------

def test_audit_underutilized_ec2():
    resources = [
        {
            "resource_id": "i-test-001",
            "resource_type": "ec2",
            "utilization_pct": 10.0,
            "monthly_cost_usd": 100.0,
            "backup_status": "healthy",
        }
    ]

    findings = audit_resources(resources, [])

    assert len(findings) == 1
    assert findings[0]["issue"] == "underutilized_ec2"
    assert findings[0]["estimated_monthly_savings_usd"] == 50.0


def test_ec2_at_threshold_is_not_flagged():
    resources = [
        {
            "resource_id": "i-test-002",
            "resource_type": "ec2",
            "utilization_pct": 15.0,
            "monthly_cost_usd": 100.0,
            "backup_status": "healthy",
        }
    ]

    findings = audit_resources(resources, [])

    assert findings == []


def test_audit_unattached_ebs():
    resources = [
        {
            "resource_id": "vol-test-001",
            "resource_type": "ebs",
            "status": "available",
            "monthly_cost_usd": 40.0,
            "backup_status": "healthy",
            "metadata": {"attached": False},
        }
    ]

    findings = audit_resources(resources, [])

    assert len(findings) == 1
    assert findings[0]["issue"] == "unattached_ebs"
    assert findings[0]["estimated_monthly_savings_usd"] == 40.0


def test_audit_missing_and_outdated_backups():
    resources = [
        {
            "resource_id": "db-test-001",
            "resource_type": "rds",
            "backup_status": "missing",
            "monthly_cost_usd": 100.0,
        },
        {
            "resource_id": "db-test-002",
            "resource_type": "rds",
            "backup_status": "outdated",
            "monthly_cost_usd": 200.0,
        },
    ]

    findings = audit_resources(resources, [])

    assert len(findings) == 2
    assert findings[0]["issue"] == "missing_backup"
    assert findings[1]["issue"] == "outdated_backup"


def test_summarize_traffic_impact():
    traffic_logs = [
        {
            "endpoint": "/api/products",
            "request_count": 1000,
            "bot_requests": 800,
            "bot_flagged": True,
            "network_out_gb": 10.0,
        },
        {
            "endpoint": "/api/login",
            "request_count": 1000,
            "bot_requests": 200,
            "bot_flagged": False,
            "network_out_gb": 5.0,
        },
    ]

    summary = summarize_traffic_impact(traffic_logs)

    assert summary["total_requests"] == 2000
    assert summary["bot_share_pct"] == 50.0
    assert summary["flagged_endpoints"] == ["/api/products"]
    assert summary["estimated_daily_cost_impact_usd"] == 0.72
    assert summary["estimated_monthly_cost_impact_usd"] == 21.6


# -------------------------
# Simulation API tests
# -------------------------

def test_simulate_iam_breach():
    response = client.post(
        "/api/v1/simulate",
        json={"scenario": "iam_breach"},
    )

    assert response.status_code == 200

    data = response.json()

    assert set(data.keys()) == {
        "incident",
        "findings",
        "recommendations",
    }

    assert isinstance(data["incident"], dict)
    assert data["incident"]["title"] == "Potential IAM Security Breach"
    assert isinstance(data["incident"]["risk_score"], int)
    assert data["incident"]["severity"] in {"critical", "high", "medium", "low"}
    assert isinstance(data["incident"]["summary"], str)
    assert isinstance(data["incident"]["recommended_actions"], list)

    assert isinstance(data["findings"], list)
    assert len(data["findings"]) > 0
    assert all(isinstance(item, str) for item in data["findings"])

    assert isinstance(data["recommendations"], list)
    assert len(data["recommendations"]) > 0
    assert all(isinstance(item, dict) for item in data["recommendations"])


def test_simulate_bot_traffic():
    response = client.post(
        "/api/v1/simulate",
        json={"scenario": "bot_traffic"},
    )

    assert response.status_code == 200

    data = response.json()

    assert set(data.keys()) == {
        "incident",
        "findings",
        "recommendations",
    }

    assert isinstance(data["incident"], dict)
    assert data["incident"]["title"] == "Abnormal Bot Traffic Detected"
    assert isinstance(data["incident"]["risk_score"], int)
    assert data["incident"]["severity"] in {"critical", "high", "medium", "low"}
    assert isinstance(data["incident"]["summary"], str)
    assert isinstance(data["incident"]["recommended_actions"], list)

    assert isinstance(data["findings"], list)
    assert len(data["findings"]) > 0
    assert all(isinstance(item, str) for item in data["findings"])

    assert isinstance(data["recommendations"], list)
    assert len(data["recommendations"]) > 0
    assert all(isinstance(item, dict) for item in data["recommendations"])


def test_simulate_resource_waste():
    response = client.post(
        "/api/v1/simulate",
        json={"scenario": "resource_waste"},
    )

    assert response.status_code == 200

    data = response.json()

    assert set(data.keys()) == {
        "incident",
        "findings",
        "recommendations",
    }

    assert isinstance(data["incident"], dict)
    assert data["incident"]["title"] == "Cloud Resource Waste Detected"
    assert isinstance(data["incident"]["risk_score"], int)
    assert data["incident"]["severity"] in {"critical", "high", "medium", "low"}
    assert isinstance(data["incident"]["summary"], str)
    assert isinstance(data["incident"]["recommended_actions"], list)

    assert isinstance(data["findings"], list)
    assert len(data["findings"]) > 0
    assert all(isinstance(item, str) for item in data["findings"])

    assert isinstance(data["recommendations"], list)
    assert len(data["recommendations"]) > 0
    assert all(isinstance(item, dict) for item in data["recommendations"])


@pytest.mark.parametrize(
    ("scenario", "expected_resource_id"),
    [
        ("iam_breach", "i-sim-iam-001"),
        ("bot_traffic", "i-sim-web-001"),
        ("resource_waste", "i-sim-waste-001"),
    ],
)
def test_simulation_persists_alert_and_recommendations(
    isolated_database,
    scenario,
    expected_resource_id,
):
    expected_factors = {
        "iam_risk",
        "resource_impact",
        "cost_impact",
        "traffic_anomaly",
        "ml_score",
        "total_cost_delta_usd",
    }

    # Run the first simulation.
    first_response = client.post(
        "/api/v1/simulate",
        json={"scenario": scenario},
    )
    assert first_response.status_code == 200

    first_response_data = first_response.json()

    # Count recommendations after the first run.
    with isolated_database() as db:
        first_count = len(
            list(
                db.scalars(
                    select(Recommendation).where(
                        Recommendation.resource_id == expected_resource_id
                    )
                ).all()
            )
        )

    assert first_count == len(first_response_data["recommendations"])
    assert first_count > 0

    # Run the same scenario again.
    second_response = client.post(
        "/api/v1/simulate",
        json={"scenario": scenario},
    )
    assert second_response.status_code == 200

    response_data = second_response.json()

    with isolated_database() as db:
        resource = db.get(CloudResource, expected_resource_id)
        assert resource is not None
        assert resource.metadata_json["simulated"] is True

        alert = db.scalar(
            select(SecurityAlert).where(
                SecurityAlert.alert_id == f"sim_alert_{scenario}"
            )
        )

        assert alert is not None
        assert alert.resource_id == expected_resource_id
        assert alert.title == response_data["incident"]["title"]
        assert alert.ai_summary == response_data["incident"]["summary"]
        assert (
            alert.recommended_actions
            == response_data["incident"]["recommended_actions"]
        )

        # Verify all five risk factors and the total cost delta are persisted.
        assert expected_factors.issubset(alert.signal_breakdown.keys())

        assert alert.correlated_event_ids is not None
        assert isinstance(alert.correlated_event_ids, list)

        recommendations = list(
            db.scalars(
                select(Recommendation).where(
                    Recommendation.resource_id == expected_resource_id
                )
            ).all()
        )

        # Repeated simulations must preserve the recommendation count.
        assert len(recommendations) == first_count
        assert len(recommendations) == len(response_data["recommendations"])
        assert len(recommendations) > 0

        recommendation_ids = [
            recommendation.recommendation_id
            for recommendation in recommendations
        ]

        assert len(recommendation_ids) == len(set(recommendation_ids))
        assert all(
            recommendation_id.startswith("sim_")
            for recommendation_id in recommendation_ids
        )


def test_simulate_invalid_scenario():
    response = client.post(
        "/api/v1/simulate",
        json={"scenario": "invalid_scenario"},
    )

    assert response.status_code == 422
