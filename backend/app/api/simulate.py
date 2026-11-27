"""Scenario simulation endpoint for AWSense."""

from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.entities import (
    AlertSeverity,
    AlertStatus,
    BackupStatus,
    CloudResource,
    Recommendation,
    RecommendationCategory,
    RecommendationState,
    ResourceType,
)
from app.services.ai_explainer import explain_incident
from app.services.auditor import audit_resources, summarize_traffic_impact
from app.services.repository import save_alert
from app.services.risk_scorer import score_risk
from app.services.telemetry_provider import get_telemetry_provider


router = APIRouter(prefix="/api/v1", tags=["simulate"])


class SimulationRequest(BaseModel):
    scenario: Literal["iam_breach", "bot_traffic", "resource_waste"]


class SimulationIncident(BaseModel):
    title: str
    risk_score: int
    severity: str
    summary: str
    recommended_actions: list[str]


class SimulationResponse(BaseModel):
    incident: SimulationIncident
    findings: list[str]
    recommendations: list[dict[str, Any]]
    # Used for database persistence, but omitted from the public API response.
    signal_breakdown: dict[str, float] = Field(default_factory=dict, exclude=True)
    correlated_event_ids: list[str] = Field(default_factory=list, exclude=True)


SIMULATED_RESOURCES = {
    "iam_breach": {
        "resource_id": "i-sim-iam-001",
        "name": "Simulated IAM Breach Resource",
    },
    "bot_traffic": {
        "resource_id": "i-sim-web-001",
        "name": "Simulated Web Traffic Resource",
    },
    "resource_waste": {
        "resource_id": "i-sim-waste-001",
        "name": "Simulated Resource Waste",
    },
}


def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(float(value), maximum))


def _calculate_risk(
    *,
    ml_score: float,
    iam_risk: float,
    resource_impact: float,
    cost_impact: float,
    traffic_anomaly: float,
    total_cost_delta_usd: float,
) -> tuple[int, str, dict[str, float]]:
    """Calculate risk through the shared five-factor scorer."""
    scored = score_risk(
        ml_score=_clamp(ml_score, 0.0, 1.0),
        iam_risk=_clamp(iam_risk),
        resource_impact=_clamp(resource_impact),
        cost_impact=_clamp(cost_impact),
        traffic_anomaly=_clamp(traffic_anomaly),
    )

    breakdown = {
        "iam_risk": _clamp(iam_risk),
        "resource_impact": _clamp(resource_impact),
        "cost_impact": _clamp(cost_impact),
        "traffic_anomaly": _clamp(traffic_anomaly),
        "ml_score": _clamp(ml_score, 0.0, 1.0),
        "total_cost_delta_usd": round(float(total_cost_delta_usd), 2),
    }

    return round(float(scored["risk_score"])), str(scored["severity"]), breakdown


def simulate_iam_breach(provider: Any) -> SimulationResponse:
    events = provider.get_cloudtrail_events()
    suspicious_events = [
        event for event in events if event.get("is_anomalous") is True
    ]

    findings = [
        (
            f"Suspicious event: {event.get('event_name')} "
            f"by {event.get('principal')} in {event.get('region')} "
            f"(risk hint: {event.get('risk_hint')})"
        )
        for event in suspicious_events
    ]
    if not findings:
        findings.append("No suspicious IAM activity was detected.")

    iam_risk = max(
        (float(event.get("risk_hint", 0) or 0) * 100 for event in suspicious_events),
        default=0.0,
    )
    resource_impact = min(len(suspicious_events) * 20.0, 100.0)
    ml_score = _clamp(iam_risk / 100.0, 0.0, 1.0)
    risk_score, severity, breakdown = _calculate_risk(
        ml_score=ml_score,
        iam_risk=iam_risk,
        resource_impact=resource_impact,
        cost_impact=0,
        traffic_anomaly=0,
        total_cost_delta_usd=0,
    )

    actions = [
        "Disable or rotate credentials for suspicious IAM principals.",
        "Review CloudTrail events and investigate unfamiliar regions and IP addresses.",
        "Inspect security group changes and newly created EC2 instances.",
        "Enable MFA and enforce least-privilege IAM policies.",
    ]
    recommendations = [
        {
            "title": "Secure suspicious IAM credentials",
            "action": "Disable or rotate credentials for suspicious principals.",
            "category": "security",
            "priority": "critical",
        },
        {
            "title": "Review unauthorized infrastructure changes",
            "action": "Investigate unexpected security group and EC2 changes.",
            "category": "security",
            "priority": "high",
        },
    ]

    incident = SimulationIncident(
        title="Potential IAM Security Breach",
        risk_score=risk_score,
        severity=severity,
        summary=f"Detected {len(suspicious_events)} suspicious CloudTrail events.",
        recommended_actions=actions if suspicious_events else [],
    )
    return SimulationResponse(
        incident=incident,
        findings=findings,
        recommendations=recommendations if suspicious_events else [],
        signal_breakdown=breakdown,
        correlated_event_ids=[
            str(event.get("event_id"))
            for event in suspicious_events
            if event.get("event_id")
        ],
    )


def simulate_bot_traffic(provider: Any) -> SimulationResponse:
    traffic_logs = provider.get_traffic_logs()
    impact = summarize_traffic_impact(traffic_logs)

    total_requests = int(impact.get("total_requests", 0) or 0)
    bot_share = float(impact.get("bot_share_pct", 0) or 0)
    flagged_endpoints = impact.get("flagged_endpoints", [])
    daily_cost = float(impact.get("estimated_daily_cost_impact_usd", 0) or 0)
    monthly_cost = float(impact.get("estimated_monthly_cost_impact_usd", 0) or 0)

    findings = [
        f"Total requests analyzed: {total_requests:,}.",
        f"Bot traffic represents {bot_share:.2f}% of total requests.",
        f"Estimated daily cost impact: ${daily_cost:.2f}.",
        f"Estimated monthly cost impact: ${monthly_cost:.2f}.",
    ]
    findings.extend(
        f"Suspicious bot traffic detected on endpoint: {endpoint}."
        for endpoint in flagged_endpoints
    )

    cost_impact = _clamp((monthly_cost / 500.0) * 100.0)
    ml_score = _clamp(bot_share / 100.0, 0.0, 1.0)
    risk_score, severity, breakdown = _calculate_risk(
        ml_score=ml_score,
        iam_risk=0,
        resource_impact=0,
        cost_impact=cost_impact,
        traffic_anomaly=bot_share,
        total_cost_delta_usd=monthly_cost,
    )

    actions = [
        "Enable AWS WAF bot control rules.",
        "Apply rate limiting to suspicious endpoints.",
        "Block or challenge suspicious IP addresses and user agents.",
        "Monitor authentication endpoints for credential-stuffing attacks.",
    ]
    recommendations = [
        {
            "title": "Mitigate automated bot traffic",
            "action": "Configure AWS WAF and rate limiting for flagged endpoints.",
            "category": "security",
            "priority": "high",
        },
        {
            "title": "Reduce unnecessary network egress costs",
            "action": "Investigate excessive automated requests and optimize responses.",
            "category": "optimization",
            "priority": "medium",
            "estimated_monthly_savings_usd": round(monthly_cost, 2),
        },
    ]

    incident = SimulationIncident(
        title="Abnormal Bot Traffic Detected",
        risk_score=risk_score,
        severity=severity,
        summary=(
            f"Bot traffic accounts for {bot_share:.2f}% of "
            f"{total_requests:,} requests. "
            f"{len(flagged_endpoints)} endpoints were flagged."
        ),
        recommended_actions=actions if flagged_endpoints else [],
    )
    return SimulationResponse(
        incident=incident,
        findings=findings,
        recommendations=recommendations if flagged_endpoints else [],
        signal_breakdown=breakdown,
        correlated_event_ids=[
            str(log.get("event_id"))
            for log in traffic_logs
            if log.get("event_id") and log.get("is_anomalous")
        ],
    )


def simulate_resource_waste(provider: Any) -> SimulationResponse:
    resources = provider.get_resources()
    metrics = provider.get_metrics(days=30)
    audit_findings = audit_resources(resources, metrics)

    findings = [
        (
            f"{item.get('description', item.get('issue', 'Resource issue'))} "
            f"(Resource: {item.get('resource_id', 'unknown')})"
        )
        for item in audit_findings
    ]
    if not findings:
        findings.append("No resource waste or backup issues were detected.")

    recommendations = [
        {
            "title": f"Resolve {item.get('issue', 'resource issue')}",
            "action": item.get("description", "Review this resource."),
            "category": "optimization",
            "priority": "high",
            "resource_id": item.get("resource_id"),
            "estimated_monthly_savings_usd": item.get(
                "estimated_monthly_savings_usd", 0
            ),
        }
        for item in audit_findings
    ]

    total_savings = sum(
        float(item.get("estimated_monthly_savings_usd", 0) or 0)
        for item in audit_findings
    )
    resource_impact = min(len(audit_findings) * 20.0, 100.0)
    cost_impact = _clamp((total_savings / 500.0) * 100.0)
    ml_score = _clamp(resource_impact / 100.0, 0.0, 1.0)
    risk_score, severity, breakdown = _calculate_risk(
        ml_score=ml_score,
        iam_risk=0,
        resource_impact=resource_impact,
        cost_impact=cost_impact,
        traffic_anomaly=0,
        total_cost_delta_usd=total_savings,
    )

    incident = SimulationIncident(
        title="Cloud Resource Waste Detected",
        risk_score=risk_score,
        severity=severity,
        summary=(
            f"Detected {len(audit_findings)} resource issues. "
            f"Potential monthly savings: ${total_savings:.2f}."
        ),
        recommended_actions=[
            "Review and resize underutilized EC2 instances.",
            "Remove unattached EBS volumes when they are no longer needed.",
            "Enable or update backups for unprotected resources.",
            "Review monthly resource costs and utilization.",
        ] if audit_findings else [],
    )
    return SimulationResponse(
        incident=incident,
        findings=findings,
        recommendations=recommendations,
        signal_breakdown=breakdown,
        correlated_event_ids=[
            str(item.get("resource_id"))
            for item in audit_findings
            if item.get("resource_id")
        ],
    )


def _ensure_simulated_resource(db: Session, scenario: str) -> str:
    """Create or update the simulated resource required by a scenario."""
    config = SIMULATED_RESOURCES[scenario]
    resource_id = config["resource_id"]
    resource = db.get(CloudResource, resource_id)

    if resource is None:
        resource = CloudResource(
            resource_id=resource_id,
            name=config["name"],
            resource_type=ResourceType.EC2,
            region="us-east-1",
            status="running",
            utilization_pct=0.0,
            backup_status=BackupStatus.NOT_APPLICABLE,
            monthly_cost_usd=0.0,
            metadata_json={"simulated": True, "scenario": scenario},
        )
        db.add(resource)
    else:
        resource.name = config["name"]
        resource.status = "running"
        resource.metadata_json = {
            **(resource.metadata_json or {}),
            "simulated": True,
            "scenario": scenario,
        }

    db.flush()
    return resource_id


def _persist_simulation(
    db: Session,
    scenario: str,
    response: SimulationResponse,
) -> None:
    """Enrich and persist a simulated incident and its recommendations."""
    resource_id = _ensure_simulated_resource(db, scenario)

    incident_data = {
        "title": response.incident.title,
        "resource_ids": [resource_id],
        "signals": response.findings,
        "signal_breakdown": {
            **response.signal_breakdown,
            "risk_score": float(response.incident.risk_score),
            "findings_count": float(len(response.findings)),
            "recommendations_count": float(len(response.recommendations)),
        },
    }
    explanation = explain_incident(incident_data)
    response.incident.summary = explanation["summary"]
    response.incident.recommended_actions = explanation["recommended_actions"]

    save_alert(
        db,
        {
            "alert_id": f"sim_alert_{scenario}",
            "resource_id": resource_id,
            "alert_type": scenario,
            "severity": AlertSeverity(response.incident.severity.lower()),
            "risk_score": response.incident.risk_score,
            "title": response.incident.title,
            "correlated_event_ids": response.correlated_event_ids,
            "signal_breakdown": incident_data["signal_breakdown"],
            "ai_summary": explanation["summary"],
            "recommended_actions": explanation["recommended_actions"],
            "status": AlertStatus.OPEN,
        },
    )

    # Remove previous simulation recommendations for this resource first.
    db.query(Recommendation).filter(
        Recommendation.resource_id == resource_id,
        Recommendation.recommendation_id.like("sim_%"),
    ).delete(synchronize_session=False)

    recommendation_records = []
    for index, item in enumerate(response.recommendations, start=1):
        category_value = str(item.get("category", "cost")).lower()
        if category_value == "security":
            category = RecommendationCategory.SECURITY
        elif category_value == "backup":
            category = RecommendationCategory.BACKUP
        else:
            category = RecommendationCategory.COST

        recommendation_records.append(
            Recommendation(
                recommendation_id=f"sim_{scenario}_{index:03d}",
                resource_id=resource_id,
                category=category,
                title=str(item.get("title", "Simulation recommendation")),
                action=str(item.get("action", "Review this recommendation.")),
                rationale=f"Generated by the {scenario} simulation.",
                estimated_monthly_savings_usd=float(
                    item.get("estimated_monthly_savings_usd", 0.0) or 0.0
                ),
                confidence="high",
                state=RecommendationState.PENDING,
            )
        )

    if recommendation_records:
        db.add_all(recommendation_records)

    db.commit()


@router.post("/simulate", response_model=SimulationResponse)
def simulate_scenario(
    request: SimulationRequest,
    db: Session = Depends(get_db),
) -> SimulationResponse:
    provider = get_telemetry_provider("mock")

    if request.scenario == "iam_breach":
        response = simulate_iam_breach(provider)
    elif request.scenario == "bot_traffic":
        response = simulate_bot_traffic(provider)
    else:
        response = simulate_resource_waste(provider)

    _persist_simulation(db, request.scenario, response)
    return response
