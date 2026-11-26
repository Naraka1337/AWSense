"""Correlated security and cost alerts endpoint backed by SQLAlchemy, ML, and 5-factor risk scoring."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.entities import (
    AlertSeverity,
    AlertStatus,
    CloudResource,
    SecurityAlert,
    TelemetryMetric,
)
from app.services.ai_explainer import explain_incident
from app.services.correlator import (
    CloudTrailEvent,
    CostDelta,
    MetricSpike,
    SignalBreakdown,
    correlate_signals,
)
from app.services.ml_detector import score_metrics
from app.services.repository import list_alerts
from app.services.risk_scorer import score_risk

router = APIRouter(prefix="/api/v1", tags=["alerts"])


class AlertItem(BaseModel):
    """Correlated security or cost incident exposed by GET /api/v1/alerts."""

    alert_id: str
    resource_id: str | None = None
    resource_ids: list[str] = Field(default_factory=list)
    alert_type: str
    severity: AlertSeverity
    risk_score: float = Field(ge=0.0, le=100.0)
    ml_score: float | None = Field(default=None, ge=0.0, le=1.0)
    title: str
    correlated_event_ids: list[str] = Field(default_factory=list)
    signal_breakdown: SignalBreakdown
    summary: str
    recommended_actions: list[str] = Field(default_factory=list)
    status: AlertStatus
    created_at: datetime


class AlertsResponse(BaseModel):
    """Response payload for GET /api/v1/alerts."""

    total: int
    alerts: list[AlertItem]


class AlertStatusUpdateRequest(BaseModel):
    """Status transition payload for POST /api/v1/alerts/{alert_id}/status."""

    status: AlertStatus


class AlertStatusUpdateResponse(BaseModel):
    """Response payload returned after updating an alert's lifecycle status."""

    alert: AlertItem
    previous_status: AlertStatus
    message: str


def _build_sample_alerts() -> tuple[AlertItem, ...]:
    """Generate deterministic static alerts via the correlation engine."""
    incidents = correlate_signals(
        cloudtrail_events=[
            CloudTrailEvent(
                event_id="ct-9001",
                timestamp="2026-11-21T02:14:00Z",
                event_name="ConsoleLogin",
                region="ap-southeast-1",
                principal="ci-deploy-temp",
                source_ip="185.220.101.42",
                is_anomalous=True,
                risk_hint=0.92,
            ),
            CloudTrailEvent(
                event_id="ct-9002",
                timestamp="2026-11-21T02:19:00Z",
                event_name="AuthorizeSecurityGroupIngress",
                region="ap-southeast-1",
                principal="ci-deploy-temp",
                resource_id="sg-0f8899aabbccdd",
                is_anomalous=True,
                risk_hint=0.88,
            ),
            CloudTrailEvent(
                event_id="ct-9003",
                timestamp="2026-11-21T02:23:00Z",
                event_name="RunInstances",
                region="ap-southeast-1",
                principal="ci-deploy-temp",
                resource_id="i-0f9e8d7c6b5a49999",
                is_anomalous=True,
                risk_hint=0.94,
            ),
            CloudTrailEvent(
                event_id="ct-9010",
                timestamp="2026-11-20T16:10:00Z",
                event_name="ModifyDBInstance",
                region="us-east-1",
                principal="ops-maintenance",
                resource_id="db-prod-orders-01",
                is_anomalous=False,
                risk_hint=0.52,
            ),
        ],
        metric_spikes=[
            MetricSpike(
                event_id="cw-9004",
                timestamp="2026-11-21T02:35:00Z",
                resource_id="i-0f9e8d7c6b5a49999",
                metric_name="CPUUtilization",
                value=96.2,
                baseline=12.0,
                region="ap-southeast-1",
                anomaly_score=0.93,
            ),
            MetricSpike(
                event_id="cw-9021",
                timestamp="2026-11-20T19:05:00Z",
                resource_id="i-0a1b2c3d4e5f60002",
                metric_name="RequestCount",
                value=2410000.0,
                baseline=148500.0,
                region="us-east-1",
                anomaly_score=0.86,
            ),
            MetricSpike(
                event_id="cw-9022",
                timestamp="2026-11-20T19:15:00Z",
                resource_id="i-0a1b2c3d4e5f60002",
                metric_name="CPUUtilization",
                value=91.4,
                baseline=31.0,
                region="us-east-1",
                anomaly_score=0.81,
            ),
            MetricSpike(
                event_id="cw-9011",
                timestamp="2026-11-20T16:28:00Z",
                resource_id="db-prod-orders-01",
                metric_name="CPUUtilization",
                value=64.0,
                baseline=35.0,
                region="us-east-1",
                anomaly_score=0.45,
            ),
        ],
        cost_deltas=[
            CostDelta(
                event_id="ce-9005",
                timestamp="2026-11-21T02:50:00Z",
                service="AmazonEC2",
                delta_usd=420.50,
                baseline_usd=65.00,
                delta_pct=646.9,
                resource_id="i-0f9e8d7c6b5a49999",
                region="ap-southeast-1",
            ),
            CostDelta(
                event_id="ce-9023",
                timestamp="2026-11-20T19:35:00Z",
                service="AWSDataTransfer",
                delta_usd=138.20,
                baseline_usd=28.00,
                delta_pct=493.6,
                resource_id="i-0a1b2c3d4e5f60002",
                region="us-east-1",
            ),
        ],
        time_window_minutes=60,
        min_signals=2,
    )

    items: list[AlertItem] = []
    for index, inc in enumerate(incidents):
        alert_status = AlertStatus.INVESTIGATING if index == 1 else AlertStatus.OPEN
        items.append(
            AlertItem(
                alert_id=f"alert_{inc.incident_id}",
                resource_id=inc.primary_resource_id,
                resource_ids=inc.resource_ids,
                alert_type=inc.incident_type,
                severity=inc.severity,
                risk_score=inc.risk_score,
                title=inc.title,
                correlated_event_ids=inc.correlated_event_ids,
                signal_breakdown=inc.signal_breakdown,
                summary=inc.summary,
                recommended_actions=inc.recommended_actions,
                status=alert_status,
                created_at=inc.window_end,
            )
        )
    return tuple(items)


_SAMPLE_ALERTS = _build_sample_alerts()


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _datetime_sort_key(value: datetime) -> float:
    """Normalize naive and timezone-aware datetimes for sorting."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


def _normalize_breakdown(
    raw: dict[str, Any] | None,
    alert: Any | None = None,
) -> SignalBreakdown:
    """Normalize stored signal breakdowns to the API response schema."""
    data = raw or {}
    risk_score = getattr(alert, "risk_score", 0.0)
    alert_type = getattr(alert, "alert_type", "")

    return SignalBreakdown(
        cloudtrail_count=int(data.get("cloudtrail_count", 0)),
        metric_spike_count=int(data.get("metric_spike_count", 0)),
        cost_delta_count=int(data.get("cost_delta_count", 0)),
        iam_risk=float(
            data.get(
                "iam_risk",
                risk_score if alert_type == "iam_breach" else 0.0,
            )
        ),
        resource_impact=float(
            data.get("resource_impact", data.get("risk_score", risk_score))
        ),
        cost_impact=float(data.get("cost_impact", 0.0)),
        traffic_anomaly=float(
            data.get(
                "traffic_anomaly",
                risk_score if alert_type == "bot_traffic" else 0.0,
            )
        ),
        total_cost_delta_usd=float(data.get("total_cost_delta_usd", 0.0)),
    )


def _compute_ml_scores_by_resource(db: Session) -> dict[str, float]:
    """Compute peak ML anomaly score per resource from stored telemetry."""
    rows = list(db.scalars(select(TelemetryMetric)).all())
    if not rows:
        return {}

    records_by_resource: dict[str, list[dict[str, Any]]] = {}
    baseline_rows: list[dict[str, Any]] = []

    for row in rows:
        payload = {
            "resource_id": row.resource_id,
            "cpu_utilization": float(row.cpu_utilization),
            "network_in_bytes": float(row.network_in_bytes),
            "network_out_bytes": float(row.network_out_bytes),
            "request_count": int(row.request_count),
        }
        records_by_resource.setdefault(row.resource_id, []).append(payload)
        if row.cpu_utilization < 80.0 and row.request_count < 1_000_000:
            baseline_rows.append(payload)

    if len(baseline_rows) < 10:
        return {}

    scores_by_resource: dict[str, float] = {}
    for resource_id, target_rows in records_by_resource.items():
        scores = score_metrics(baseline_rows, target_rows)
        if scores:
            scores_by_resource[resource_id] = round(max(scores), 4)
    return scores_by_resource


def _build_security_group_resource_map(db: Session) -> dict[str, list[str]]:
    """Map security group IDs stored in resource metadata to their compute resource IDs."""
    sg_map: dict[str, list[str]] = {}
    for res in db.scalars(select(CloudResource)).all():
        meta = res.metadata_json or {}
        sg_id = meta.get("security_group")
        if isinstance(sg_id, str) and sg_id:
            sg_map.setdefault(sg_id, []).append(res.resource_id)
    return sg_map


def _resolve_alert_ml_score(
    alert: Any,
    ml_scores: dict[str, float] | None,
    sg_map: dict[str, list[str]] | None,
) -> tuple[float | None, list[str]]:
    """Resolve an alert's ML score and linked resource IDs across direct, SG, or summary matches."""
    rid = getattr(alert, "resource_id", None)
    resource_ids = [rid] if rid else []

    if rid and sg_map and rid in sg_map:
        for linked_id in sg_map[rid]:
            if linked_id not in resource_ids:
                resource_ids.append(linked_id)

    if ml_scores:
        direct_scores = [ml_scores[cand] for cand in resource_ids if cand in ml_scores]
        if direct_scores:
            return max(direct_scores), resource_ids

        searchable_text = f"{getattr(alert, 'title', '') or ''} {getattr(alert, 'ai_summary', '') or ''}"
        matched_ids = [cand for cand in sorted(ml_scores) if cand in searchable_text]
        if matched_ids:
            for cand in matched_ids:
                if cand not in resource_ids:
                    resource_ids.append(cand)
            return max(ml_scores[cand] for cand in matched_ids), resource_ids

    raw_breakdown = getattr(alert, "signal_breakdown", None) or {}
    if "ml_score" in raw_breakdown and raw_breakdown["ml_score"] is not None:
        return round(_clamp(float(raw_breakdown["ml_score"]), 0.0, 1.0), 4), resource_ids

    return None, resource_ids


def _convert_db_alert(
    alert: Any,
    ml_scores: dict[str, float] | None = None,
    sg_map: dict[str, list[str]] | None = None,
) -> AlertItem:
    """Convert a SQLAlchemy SecurityAlert into the API response schema."""
    breakdown = _normalize_breakdown(alert.signal_breakdown, alert)
    ml_score, resource_ids = _resolve_alert_ml_score(alert, ml_scores, sg_map)

    risk_score = float(alert.risk_score)
    severity = alert.severity
    if ml_score is not None:
        scored = score_risk(
            ml_score=_clamp(ml_score, 0.0, 1.0),
            iam_risk=_clamp(breakdown.iam_risk, 0.0, 100.0),
            resource_impact=_clamp(breakdown.resource_impact, 0.0, 100.0),
            cost_impact=_clamp(breakdown.cost_impact, 0.0, 100.0),
            traffic_anomaly=_clamp(breakdown.traffic_anomaly, 0.0, 100.0),
        )
        risk_score = float(scored["risk_score"])
        severity = AlertSeverity(str(scored["severity"]))

    summary = alert.ai_summary or ""
    actions = list(alert.recommended_actions or [])

    if not summary or not actions:
        explained = explain_incident(
            {
                "title": alert.title,
                "resource_ids": resource_ids,
                "signals": [
                    {"event_id": event_id}
                    for event_id in (alert.correlated_event_ids or [])
                ],
                "signal_breakdown": breakdown.model_dump(),
            }
        )
        summary = summary or explained["summary"]
        if not actions:
            actions = explained["recommended_actions"]

    return AlertItem(
        alert_id=alert.alert_id,
        resource_id=alert.resource_id,
        resource_ids=resource_ids,
        alert_type=alert.alert_type,
        severity=severity,
        risk_score=risk_score,
        ml_score=ml_score,
        title=alert.title,
        correlated_event_ids=alert.correlated_event_ids or [],
        signal_breakdown=breakdown,
        summary=summary,
        recommended_actions=actions,
        status=alert.status,
        created_at=alert.created_at,
    )


@router.get("/alerts", response_model=AlertsResponse)
def get_alerts(
    severity: AlertSeverity | None = Query(default=None),
    status: AlertStatus | None = Query(default=None),
    db: Session = Depends(get_db),
) -> AlertsResponse:
    """Return persisted alerts (falling back to sample alerts when DB is empty) with optional filters."""
    items: list[AlertItem] = []

    # Depends is not resolved when this function is called directly in tests.
    if isinstance(db, Session):
        db_alerts = list_alerts(db)
        if db_alerts:
            ml_scores = _compute_ml_scores_by_resource(db)
            sg_map = _build_security_group_resource_map(db)
            items = [
                _convert_db_alert(db_alert, ml_scores, sg_map)
                for db_alert in db_alerts
            ]

    if not items:
        items = [alert.model_copy(deep=True) for alert in _SAMPLE_ALERTS]

    filtered = [
        alert
        for alert in items
        if (severity is None or alert.severity == severity)
        and (status is None or alert.status == status)
    ]

    filtered.sort(
        key=lambda alert: (
            alert.risk_score,
            _datetime_sort_key(alert.created_at),
        ),
        reverse=True,
    )

    return AlertsResponse(
        total=len(filtered),
        alerts=filtered,
    )


@router.post(
    "/alerts/{alert_id}/status",
    response_model=AlertStatusUpdateResponse,
)
def update_alert_status(
    alert_id: str,
    payload: AlertStatusUpdateRequest,
    db: Session = Depends(get_db),
) -> AlertStatusUpdateResponse:
    """Update a persisted alert's lifecycle status ('open', 'investigating', 'resolved', 'dismissed')."""
    existing = db.get(SecurityAlert, alert_id)
    if existing is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Alert '{alert_id}' not found",
        )

    previous_status = existing.status
    existing.status = payload.status
    db.commit()
    db.refresh(existing)

    ml_scores = _compute_ml_scores_by_resource(db)
    sg_map = _build_security_group_resource_map(db)

    return AlertStatusUpdateResponse(
        alert=_convert_db_alert(existing, ml_scores, sg_map),
        previous_status=previous_status,
        message=(
            f"Alert '{alert_id}' updated from "
            f"'{previous_status.value}' to '{existing.status.value}'"
        ),
    )
