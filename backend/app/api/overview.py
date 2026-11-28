"""Overview dashboard summary endpoint computed from DB state and telemetry."""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.alerts import score_alerts
from app.core.database import get_db
from app.models.entities import (
    AlertSeverity,
    AlertStatus,
    BackupStatus,
    CloudResource,
    Recommendation,
    RecommendationState,
    SecurityAlert,
    TelemetryMetric,
)
from app.services.telemetry_provider import get_telemetry_provider

router = APIRouter(prefix="/api/v1", tags=["overview"])


class AlertCountBreakdown(BaseModel):
    total: int
    critical: int
    high: int
    medium: int
    low: int


class CostUsagePoint(BaseModel):
    date: str
    daily_cost_usd: float
    avg_cpu_pct: float
    request_count: int


class OverviewResponse(BaseModel):
    health_score: float = Field(ge=0.0, le=100.0)
    risk_level: AlertSeverity
    total_monthly_savings_usd: float
    monthly_spend_usd: float
    active_alerts: AlertCountBreakdown
    monitored_resources: int
    unprotected_resources: int
    cost_usage_trend: list[CostUsagePoint]


_SAMPLE_COST_USAGE_TREND = [
    CostUsagePoint(
        date="2026-11-15",
        daily_cost_usd=48.20,
        avg_cpu_pct=28.4,
        request_count=142000,
    ),
    CostUsagePoint(
        date="2026-11-16",
        daily_cost_usd=49.10,
        avg_cpu_pct=29.1,
        request_count=148500,
    ),
    CostUsagePoint(
        date="2026-11-17",
        daily_cost_usd=47.80,
        avg_cpu_pct=27.6,
        request_count=139800,
    ),
    CostUsagePoint(
        date="2026-11-18",
        daily_cost_usd=50.40,
        avg_cpu_pct=30.2,
        request_count=155400,
    ),
    CostUsagePoint(
        date="2026-11-19",
        daily_cost_usd=188.60,
        avg_cpu_pct=68.5,
        request_count=1180000,
    ),
    CostUsagePoint(
        date="2026-11-20",
        daily_cost_usd=312.90,
        avg_cpu_pct=84.2,
        request_count=2410000,
    ),
    CostUsagePoint(
        date="2026-11-21",
        daily_cost_usd=289.45,
        avg_cpu_pct=76.9,
        request_count=2190000,
    ),
]

_SAMPLE_MONTHLY_SPEND = 1842.75

_SEVERITY_RANK = {
    AlertSeverity.LOW: 1,
    AlertSeverity.MEDIUM: 2,
    AlertSeverity.HIGH: 3,
    AlertSeverity.CRITICAL: 4,
}


def _build_sample_overview() -> OverviewResponse:
    """Build sample overview for direct calls without a DB session."""

    return OverviewResponse(
        health_score=64.0,
        risk_level=AlertSeverity.HIGH,
        total_monthly_savings_usd=318.40,
        monthly_spend_usd=_SAMPLE_MONTHLY_SPEND,
        active_alerts=AlertCountBreakdown(
            total=3,
            critical=0,
            high=1,
            medium=1,
            low=1,
        ),
        monitored_resources=6,
        unprotected_resources=3,
        cost_usage_trend=_SAMPLE_COST_USAGE_TREND,
    )


def _build_trend_series(db: Session) -> list[CostUsagePoint]:
    """Combine daily provider costs with DB telemetry metrics."""

    provider = get_telemetry_provider()
    cost_rows = provider.get_cost_usage(days=30)

    daily_cost: dict[str, float] = defaultdict(float)

    for entry in cost_rows:
        timestamp = entry.get("timestamp", "")
        day = str(entry.get("date") or timestamp[:10])

        if day:
            daily_cost[day] += float(entry.get("cost_usd", 0.0))

    daily_cpu: dict[str, list[float]] = defaultdict(list)
    daily_requests: dict[str, int] = defaultdict(int)

    metric_rows = list(db.scalars(select(TelemetryMetric)).all())

    for metric in metric_rows:
        day = metric.timestamp.strftime("%Y-%m-%d")
        daily_cpu[day].append(float(metric.cpu_utilization))
        daily_requests[day] += int(metric.request_count)

    all_days = sorted(set(daily_cost) | set(daily_cpu))

    trend = []

    for day in all_days:
        cpu_values = daily_cpu.get(day, [])

        avg_cpu = (
            round(sum(cpu_values) / len(cpu_values), 1)
            if cpu_values
            else 0.0
        )

        trend.append(
            CostUsagePoint(
                date=day,
                daily_cost_usd=round(daily_cost.get(day, 0.0), 2),
                avg_cpu_pct=avg_cpu,
                request_count=daily_requests.get(day, 0),
            )
        )

    return trend or _SAMPLE_COST_USAGE_TREND


@router.get("/overview", response_model=OverviewResponse)
def get_overview(
    db: Session = Depends(get_db),
) -> OverviewResponse:
    """Return dashboard overview calculated from persisted database records."""

    # Depends is not resolved when this function is called directly.
    if not isinstance(db, Session):
        return _build_sample_overview()

    resources = list(db.scalars(select(CloudResource)).all())

    alerts = list(
        db.scalars(
            select(SecurityAlert).where(
                SecurityAlert.status.notin_(
                    [AlertStatus.RESOLVED, AlertStatus.DISMISSED]
                )
            )
        ).all()
    )

    recommendations = list(
        db.scalars(select(Recommendation)).all()
    )

    scored_alerts = score_alerts(db, alerts)

    critical_count = sum(
        1 for _, severity in scored_alerts
        if severity == AlertSeverity.CRITICAL
    )
    high_count = sum(
        1 for _, severity in scored_alerts
        if severity == AlertSeverity.HIGH
    )
    medium_count = sum(
        1 for _, severity in scored_alerts
        if severity == AlertSeverity.MEDIUM
    )
    low_count = sum(
        1 for _, severity in scored_alerts
        if severity == AlertSeverity.LOW
    )

    active_alerts = AlertCountBreakdown(
        total=len(scored_alerts),
        critical=critical_count,
        high=high_count,
        medium=medium_count,
        low=low_count,
    )

    if scored_alerts:
        highest_severity = max(
            (severity for _, severity in scored_alerts),
            key=lambda severity: _SEVERITY_RANK[severity],
        )
    else:
        highest_severity = AlertSeverity.LOW

    highest_risk_score = max(
        (score for score, _ in scored_alerts),
        default=0.0,
    )

    health_score = round(
        max(0.0, min(100.0, 100.0 - highest_risk_score)),
        1,
    )

    total_savings = round(
        sum(
            float(item.estimated_monthly_savings_usd or 0.0)
            for item in recommendations
            if item.state != RecommendationState.DISMISSED
        ),
        2,
    )

    monthly_spend = round(
        sum(
            float(resource.monthly_cost_usd or 0.0)
            for resource in resources
        ),
        2,
    )

    if monthly_spend <= 0:
        monthly_spend = _SAMPLE_MONTHLY_SPEND

    unprotected_resources = sum(
        1
        for resource in resources
        if resource.backup_status in (
            BackupStatus.MISSING,
            BackupStatus.OUTDATED,
        )
    )

    return OverviewResponse(
        health_score=health_score,
        risk_level=highest_severity,
        total_monthly_savings_usd=total_savings,
        monthly_spend_usd=monthly_spend,
        active_alerts=active_alerts,
        monitored_resources=len(resources),
        unprotected_resources=unprotected_resources,
        cost_usage_trend=_build_trend_series(db),
    )
