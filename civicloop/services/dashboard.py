"""Supervisor dashboard numbers, computed from the live tables.

Every figure has a definition a supervisor can read on the screen. Two things are deliberate:
- Simulated history (the "Synthetic history" account used for model training) is excluded.
- SLA hours are pilot defaults, not statute. Indian cities publish 12 hours to one week by complaint
  type, and the sources are secondary, so they are configurable here and shown on the dashboard.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from civicloop.models import (
    AnalysisResult,
    Incident,
    IncidentStatus,
    RiskAssessment,
    RoutePlan,
    RouteStop,
    User,
    UserRole,
    VerificationRecord,
    VerificationStatus,
    WorkOrder,
    WorkOrderStatus,
)
from civicloop.synthetic import SYNTHETIC_LIKE

SLA_HOURS = {"critical": 12, "high": 24, "medium": 48, "low": 72, "unrated": 48}
OPEN = {
    IncidentStatus.PENDING_ANALYSIS,
    IncidentStatus.READY_FOR_REVIEW,
    IncidentStatus.APPROVED,
    IncidentStatus.IN_PROGRESS,
    IncidentStatus.UNCERTAIN,
}
CLOCK_STOPPED = {IncidentStatus.RESOLVED, IncidentStatus.VERIFIED, IncidentStatus.REJECTED}
AGE_BUCKETS = [("under 1 day", 0, 24), ("1 to 3 days", 24, 72), ("3 to 7 days", 72, 168), ("over 7 days", 168, 10**9)]
GRID = 0.0045  # about 500 m of latitude


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return _utc(value).isoformat() if value else None


class DashboardService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # ------------------------------------------------------------------ shared loading

    def _incidents(self, now: datetime, history_days: int = 90) -> list[Incident]:
        synthetic = self.session.scalar(select(User.id).where(User.email.like(SYNTHETIC_LIKE)))
        since = now - timedelta(days=history_days)
        rows = self.session.scalars(select(Incident).where(Incident.created_at >= since)).all()
        rows += self.session.scalars(select(Incident).where(Incident.status.in_(OPEN), Incident.created_at < since)).all()
        return [i for i in rows if i.reporter_id != synthetic or synthetic is None]

    def _severity_and_risk(self, ids: list[str]) -> tuple[dict[str, str | None], dict[str, float]]:
        severity: dict[str, str | None] = {}
        risk: dict[str, float] = {}
        if not ids:
            return severity, risk
        for a in self.session.scalars(select(AnalysisResult).where(AnalysisResult.incident_id.in_(ids)).order_by(AnalysisResult.created_at)):
            severity[a.incident_id] = a.severity
        for r in self.session.scalars(select(RiskAssessment).where(RiskAssessment.incident_id.in_(ids)).order_by(RiskAssessment.created_at)):
            risk[r.incident_id] = r.score
        return severity, risk

    @staticmethod
    def _sla_hours(severity: str | None) -> int:
        return SLA_HOURS.get((severity or "").lower(), SLA_HOURS["unrated"])

    # ------------------------------------------------------------------ map

    def map_points(self, include_closed_days: int = 7) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        incidents = self._incidents(now, history_days=max(include_closed_days, 1))
        severity, risk = self._severity_and_risk([i.id for i in incidents])
        points = []
        for i in incidents:
            created = _utc(i.created_at)
            closed = i.status in CLOCK_STOPPED
            if closed and _utc(i.updated_at) < now - timedelta(days=include_closed_days):
                continue
            sev = severity.get(i.id)
            age_h = (now - created).total_seconds() / 3600
            points.append(
                {
                    "id": i.id,
                    "latitude": i.latitude,
                    "longitude": i.longitude,
                    "status": i.status.value,
                    "severity": sev,
                    "risk": risk.get(i.id),
                    "age_hours": round(age_h, 1),
                    "breached": (not closed) and age_h > self._sla_hours(sev),
                    "description": i.description,
                }
            )
        return points

    # ------------------------------------------------------------------ summary

    def summary(self, days: int = 14) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        incidents = self._incidents(now, history_days=90)
        severity, risk = self._severity_and_risk([i.id for i in incidents])
        by_id = {i.id: i for i in incidents}
        open_items = [i for i in incidents if i.status in OPEN]

        def age_h(i: Incident) -> float:
            return (now - _utc(i.created_at)).total_seconds() / 3600

        counts: dict[str, int] = defaultdict(int)
        for i in open_items:
            counts[i.status.value] += 1

        # ---- needs review
        ready = [i for i in open_items if i.status == IncidentStatus.READY_FOR_REVIEW]
        oldest_review = max((age_h(i) for i in ready), default=0.0)

        # ---- SLA
        breached = [i for i in open_items if age_h(i) > self._sla_hours(severity.get(i.id))]
        at_risk = [i for i in open_items if i not in breached and age_h(i) > 0.75 * self._sla_hours(severity.get(i.id))]
        recent_closed = [
            i for i in incidents if i.status in CLOCK_STOPPED and i.status != IncidentStatus.REJECTED and _utc(i.updated_at) >= now - timedelta(days=30)
        ]
        on_time = [i for i in recent_closed if (_utc(i.updated_at) - _utc(i.created_at)).total_seconds() / 3600 <= self._sla_hours(severity.get(i.id))]
        on_time_pct = len(on_time) / len(recent_closed) if recent_closed else None

        # ---- dispatch and field
        orders = self.session.scalars(select(WorkOrder).where(WorkOrder.status.in_([WorkOrderStatus.DRAFT, WorkOrderStatus.APPROVED, WorkOrderStatus.ASSIGNED, WorkOrderStatus.IN_PROGRESS]))).all()
        routed = {s.work_order_id for s in self.session.scalars(select(RouteStop))}
        plans = self.session.scalars(select(RoutePlan)).all()
        unassigned = [o for o in orders if o.status == WorkOrderStatus.APPROVED]
        unrouted = [o for o in orders if o.status in {WorkOrderStatus.APPROVED, WorkOrderStatus.ASSIGNED} and o.id not in routed]
        in_field = [o for o in orders if o.status in {WorkOrderStatus.ASSIGNED, WorkOrderStatus.IN_PROGRESS}]

        # ---- evidence
        records = self.session.scalars(select(VerificationRecord).where(VerificationRecord.status == VerificationStatus.UNCERTAIN)).all()
        seen: set[str] = set()
        uncertain_evidence = []
        for v in records:  # one entry per incident, only while the incident is still waiting on that decision
            if v.incident_id in by_id and v.incident_id not in seen and by_id[v.incident_id].status == IncidentStatus.UNCERTAIN:
                seen.add(v.incident_id)
                uncertain_evidence.append(v)

        # ---- outcomes (30 days)
        done30 = [i for i in incidents if i.status in {IncidentStatus.RESOLVED, IncidentStatus.VERIFIED} and _utc(i.updated_at) >= now - timedelta(days=30)]
        verified30 = [i for i in done30 if i.status == IncidentStatus.VERIFIED]
        closure_rate = len(verified30) / len(done30) if done30 else None
        hours_to_close = [(_utc(i.updated_at) - _utc(i.created_at)).total_seconds() / 3600 for i in verified30]
        median_close = statistics.median(hours_to_close) if hours_to_close else None

        # ---- flow, last N days
        flow = []
        today = now.date()
        for d in range(days - 1, -1, -1):
            day = today - timedelta(days=d)
            flow.append(
                {
                    "date": day.isoformat(),
                    "created": sum(1 for i in incidents if _utc(i.created_at).date() == day),
                    "closed": sum(1 for i in incidents if i.status in CLOCK_STOPPED and _utc(i.updated_at).date() == day),
                }
            )

        # ---- backlog age buckets by status
        statuses = ["pending_analysis", "ready_for_review", "approved", "in_progress", "uncertain"]
        aging = {s: [0] * len(AGE_BUCKETS) for s in statuses}
        for i in open_items:
            h = age_h(i)
            for b, (_, lo, hi) in enumerate(AGE_BUCKETS):
                if lo <= h < hi:
                    aging[i.status.value][b] += 1
                    break

        # ---- repeat sites: 500 m grid cells with 3+ reports in 90 days
        recent = [i for i in incidents if i.status != IncidentStatus.REJECTED and _utc(i.created_at) >= now - timedelta(days=90)]
        cells: dict[tuple[int, int], list[Incident]] = defaultdict(list)
        for i in recent:
            cells[(round(i.latitude / GRID), round(i.longitude / GRID))].append(i)
        repeat_cells = [group for group in cells.values() if len(group) >= 3]
        hotspots = sorted(
            (
                {
                    "latitude": sum(i.latitude for i in g) / len(g),
                    "longitude": sum(i.longitude for i in g) / len(g),
                    "reports_90d": len(g),
                    "open": sum(1 for i in g if i.status in OPEN),
                    "last_reported": _iso(max(_utc(i.created_at) for i in g)),
                    "sample": g[0].description,
                    "incident_id": max(g, key=lambda x: _utc(x.created_at)).id,
                }
                for g in repeat_cells
            ),
            key=lambda h: -h["reports_90d"],
        )[:6]
        repeat_reports = sum(len(g) for g in repeat_cells)

        # ---- crew workload
        workers = self.session.scalars(select(User).where(User.role == UserRole.SANITATION_WORKER, User.is_active.is_(True))).all()
        workload = []
        for w in workers:
            mine = [o for o in orders if o.assigned_to == w.id]
            workload.append({"worker_id": w.id, "name": w.name, "active_jobs": len(mine), "in_progress": sum(1 for o in mine if o.status == WorkOrderStatus.IN_PROGRESS)})

        # ---- attention list, most urgent first
        attention: list[dict[str, Any]] = []

        def item(kind: str, reason: str, i: Incident, priority: int) -> dict[str, Any]:
            return {
                "kind": kind,
                "reason": reason,
                "priority": priority,
                "incident": {"id": i.id, "description": i.description, "status": i.status.value, "latitude": i.latitude, "longitude": i.longitude},
                "severity": severity.get(i.id),
                "risk": risk.get(i.id),
                "age_hours": round(age_h(i), 1),
            }

        for i in sorted(breached, key=lambda x: -age_h(x)):
            over = age_h(i) - self._sla_hours(severity.get(i.id))
            attention.append(item("sla_breach", f"{over:.0f} h past its {self._sla_hours(severity.get(i.id))} h target", i, 0))
        for v in uncertain_evidence:
            attention.append(item("evidence", "Cleanup evidence needs your decision", by_id[v.incident_id], 1))
        for i in sorted(ready, key=lambda x: -(risk.get(x.id) or 0)):
            if i not in breached:
                attention.append(item("review", "Waiting for your review", i, 2))
        for o in unassigned:
            inc = by_id.get(o.incident_id)
            if inc and inc not in breached:
                attention.append(item("dispatch", "Approved, no worker assigned", inc, 3))
        attention.sort(key=lambda a: (a["priority"], -(a["risk"] or 0), -a["age_hours"]))

        return {
            "generated_at": now.isoformat(),
            "sla_hours": SLA_HOURS,
            "counts": dict(counts),
            "kpis": {
                "needs_review": {
                    "count": len(ready),
                    "oldest_hours": round(oldest_review, 1),
                    "within_target_pct": (sum(1 for i in ready if i not in breached) / len(ready)) if ready else None,
                },
                "sla": {
                    "open": len(open_items),
                    "breached": len(breached),
                    "at_risk": len(at_risk),
                    "on_time_pct_30d": on_time_pct,
                    "closed_30d": len(recent_closed),
                },
                "dispatch": {
                    "unassigned_orders": len(unassigned),
                    "unrouted_orders": len(unrouted),
                    "routes_awaiting_approval": sum(1 for p in plans if p.approved_by is None),
                    "routes_approved": sum(1 for p in plans if p.approved_by is not None),
                },
                "in_field": {"jobs": len(in_field), "in_progress": sum(1 for o in in_field if o.status == WorkOrderStatus.IN_PROGRESS)},
                "evidence_to_review": len(uncertain_evidence),
                "verified_closure_rate_30d": closure_rate,
                "median_hours_to_close_30d": median_close,
                "verified_within_24h_pct_30d": (sum(1 for h in hours_to_close if h <= 24) / len(hours_to_close)) if hours_to_close else None,
                "repeat_sites": {
                    "count": len(repeat_cells),
                    "share_of_reports": (repeat_reports / len(recent)) if recent else None,
                    "reports_90d": len(recent),
                },
            },
            "flow": flow,
            "aging": {"buckets": [b[0] for b in AGE_BUCKETS], "series": aging},
            "hotspots": hotspots,
            "workload": sorted(workload, key=lambda w: -w["active_jobs"]),
            "attention": attention[:10],
        }
