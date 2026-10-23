"""Supervisor dashboard numbers: counted from real rows, with age and SLA logic."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from civicloop.api import create_app
from civicloop.jobs import InMemoryJobQueue
from civicloop.models import AnalysisResult, Incident, IncidentStatus, ReporterType, User, UserRole
from civicloop.storage import InMemoryObjectStorage

PASSWORD = "correct horse battery"


@pytest.fixture()
def world(tmp_path):
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'dash.db'}",
        auth_secret="test-secret-that-is-at-least-32-characters",
        storage=InMemoryObjectStorage(),
        queue=InMemoryJobQueue(),
    )
    with TestClient(app) as client:
        def account(role, email, headers=None):
            r = client.post("/api/v1/auth/register", headers=headers or {}, json={"name": role, "email": email, "password": PASSWORD, "role": role, "city": "Chandigarh", "pincode": "160017"})
            assert r.status_code == 201, r.text
            token = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()["access_token"]
            return {"Authorization": f"Bearer {token}"}, r.json()["user_id"]

        admin, _ = account("admin", "admin@x.test")
        supervisor, _ = account("supervisor", "sup@x.test", admin)
        resident, resident_id = account("reporter", "res@x.test")
        yield client, app, dict(supervisor=supervisor, resident=resident, admin=admin), resident_id


def add(app, reporter_id, text, status, hours_old, severity=None, lat=30.73, lon=76.78):
    created = datetime.now(timezone.utc) - timedelta(hours=hours_old)
    with app.state.session_factory() as session:
        incident = Incident(
            reporter_id=reporter_id, reporter_type=ReporterType.RESIDENT, description=text, latitude=lat, longitude=lon,
            occurred_at=created, status=status, created_at=created, updated_at=created if status in (IncidentStatus.PENDING_ANALYSIS, IncidentStatus.READY_FOR_REVIEW, IncidentStatus.APPROVED) else datetime.now(timezone.utc),
        )
        session.add(incident)
        session.flush()
        if severity:
            session.add(AnalysisResult(incident_id=incident.id, provider="t", model_name="t", category="x", severity=severity, confidence=0.9, extracted_details={}, raw_response={}))
        session.commit()
        return incident.id


def test_summary_counts_ages_and_sla(world):
    client, app, h, resident_id = world
    add(app, resident_id, "Fresh report awaiting analysis", IncidentStatus.PENDING_ANALYSIS, 1)
    add(app, resident_id, "High severity, 30 hours old", IncidentStatus.READY_FOR_REVIEW, 30, "high")  # 24 h target: breached
    add(app, resident_id, "Low severity, 30 hours old", IncidentStatus.READY_FOR_REVIEW, 30, "low")  # 72 h target: fine
    add(app, resident_id, "Approved this morning", IncidentStatus.APPROVED, 5, "medium")
    add(app, resident_id, "Cleaned and verified", IncidentStatus.VERIFIED, 40, "medium")  # closed inside its 48 h target

    data = client.get("/api/v1/dashboard/summary", headers=h["supervisor"]).json()
    kpis = data["kpis"]
    assert data["counts"] == {"pending_analysis": 1, "ready_for_review": 2, "approved": 1}
    assert kpis["needs_review"]["count"] == 2 and 29 < kpis["needs_review"]["oldest_hours"] < 31
    assert kpis["sla"]["open"] == 4 and kpis["sla"]["breached"] == 1
    assert kpis["sla"]["on_time_pct_30d"] == 1.0 and kpis["sla"]["closed_30d"] == 1
    assert kpis["verified_closure_rate_30d"] == 1.0
    assert kpis["needs_review"]["within_target_pct"] == 0.5  # one of the two waiting reports is past its target
    assert kpis["verified_within_24h_pct_30d"] == 0.0  # the one verified report took 40 hours
    # the breach leads the attention list, ahead of plain review items
    assert data["attention"][0]["kind"] == "sla_breach" and "30 hours" in data["attention"][0]["incident"]["description"]
    assert data["sla_hours"]["critical"] == 12
    assert sum(sum(v) for v in data["aging"]["series"].values()) == 4
    assert len(data["flow"]) == 14 and sum(d["created"] for d in data["flow"]) == 5


def test_repeat_sites_and_map_points(world):
    client, app, h, resident_id = world
    for n in range(4):  # four reports within 500 m: a repeat site
        add(app, resident_id, f"Recurring pile {n}", IncidentStatus.READY_FOR_REVIEW, 10 + n, "medium", lat=30.7400 + n * 0.0003)
    add(app, resident_id, "Lone report elsewhere", IncidentStatus.APPROVED, 3, "low", lat=30.70, lon=76.70)

    data = client.get("/api/v1/dashboard/summary", headers=h["supervisor"]).json()
    assert data["kpis"]["repeat_sites"]["count"] == 1
    assert data["hotspots"][0]["reports_90d"] == 4
    assert abs(data["kpis"]["repeat_sites"]["share_of_reports"] - 0.8) < 1e-9

    points = client.get("/api/v1/dashboard/map", headers=h["supervisor"]).json()
    assert len(points) == 5
    assert {p["status"] for p in points} == {"ready_for_review", "approved"}
    assert all(set(p) >= {"latitude", "longitude", "status", "age_hours", "breached", "description"} for p in points)


def test_dashboard_is_for_supervisors_and_ignores_simulated_history(world):
    client, app, h, resident_id = world
    assert client.get("/api/v1/dashboard/summary", headers=h["resident"]).status_code == 403
    assert client.get("/api/v1/dashboard/map", headers=h["resident"]).status_code == 403
    assert client.get("/api/v1/dashboard/summary", headers=h["admin"]).status_code == 200

    from civicloop.synthetic import seed_synthetic_history

    with app.state.session_factory() as session:
        seed_synthetic_history(session, 60)
        assert session.scalar(select(User).where(User.role == UserRole.REPORTER, User.is_active.is_(False))) is not None
    data = client.get("/api/v1/dashboard/summary", headers=h["supervisor"]).json()
    assert data["kpis"]["repeat_sites"]["reports_90d"] == 0 and data["kpis"]["sla"]["closed_30d"] == 0
    assert client.get("/api/v1/dashboard/map", headers=h["supervisor"]).json() == []
    # ...nor does it leak into the incident list that staff work from
    for status in ("verified", "resolved", "rejected"):
        assert client.get(f"/api/v1/incidents?status_filter={status}", headers=h["supervisor"]).json() == []
