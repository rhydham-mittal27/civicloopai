"""End-to-end: the whole cleanup loop over HTTP, with role checks at every step."""

import time
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from civicloop.api import create_app
from civicloop.jobs import InMemoryJobQueue
from civicloop.storage import InMemoryObjectStorage


class FakeAdapter:
    provider = "test"
    model_name = "test-model"

    def analyze(self, payload):
        return {"category": "mixed_waste", "severity": "high", "confidence": 0.9, "details": {}}


PASSWORD = "correct horse battery"


@pytest.fixture()
def world(tmp_path):
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'ops.db'}",
        auth_secret="test-secret-that-is-at-least-32-characters",
        storage=InMemoryObjectStorage(),
        queue=InMemoryJobQueue(),
        analysis_adapter_factory=FakeAdapter,
    )
    with TestClient(app) as client:
        def make(role, email, headers=None):
            r = client.post("/api/v1/auth/register", headers=headers or {}, json={"name": role, "email": email, "password": PASSWORD, "role": role, "city": "Chandigarh", "pincode": "160017"})
            assert r.status_code == 201, r.text
            token = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()["access_token"]
            return {"Authorization": f"Bearer {token}"}, r.json()["user_id"]

        admin, admin_id = make("admin", "admin@x.test")  # first account may pick any role
        supervisor, _ = make("supervisor", "sup@x.test", admin)
        worker, worker_id = make("sanitation_worker", "work@x.test", admin)
        resident, _ = make("reporter", "res@x.test")
        other, _ = make("reporter", "other@x.test")
        yield client, dict(admin=admin, supervisor=supervisor, worker=worker, resident=resident, other=other), worker_id, admin_id


def report(client, headers, text="Overflowing bins near the market", lat=30.7333, lon=76.7794):
    r = client.post(
        "/api/v1/incidents",
        headers=headers,
        json={"reporter_type": "resident", "description": text, "latitude": lat, "longitude": lon, "occurred_at": datetime.now(timezone.utc).isoformat()},
    )
    assert r.status_code == 201, r.text
    incident_id = r.json()["id"]
    up = client.post(f"/api/v1/incidents/{incident_id}/media", headers=headers, files={"file": ("a.jpg", b"before-photo", "image/jpeg")})
    assert up.status_code == 201, up.text
    return incident_id


def test_full_cleanup_loop(world):
    client, h, worker_id, _ = world
    incident_id = report(client, h["resident"])

    # Analysis scores the hotspot automatically, and the queue is ranked.
    analysed = client.post(f"/api/v1/incidents/{incident_id}/analysis", headers=h["supervisor"])
    assert analysed.status_code == 200 and analysed.json()["risk_score"] > 0
    queue = client.get("/api/v1/queue", headers=h["supervisor"]).json()
    assert [item["incident"]["id"] for item in queue] == [incident_id]
    assert queue[0]["risk"]["factors"]["severity"] == 0.8

    # Supervisor opens a work order, approves, assigns. Approval cannot be faked via PATCH status.
    assert client.patch(f"/api/v1/incidents/{incident_id}/status", headers=h["supervisor"], json={"status": "approved"}).status_code == 409
    order = client.post(f"/api/v1/incidents/{incident_id}/work-orders", headers=h["supervisor"], json={"priority": 8, "estimated_volume": 2}).json()
    assert client.post(f"/api/v1/incidents/{incident_id}/work-orders", headers=h["supervisor"], json={"priority": 1}).status_code == 400
    assert client.post(f"/api/v1/work-orders/{order['id']}/approve", headers=h["supervisor"]).json()["status"] == "approved"

    # Routes: built for approved orders, with an honest baseline.
    route = client.post("/api/v1/routes", headers=h["supervisor"], json={"work_order_ids": [order["id"]], "vehicle_capacity": 10})
    assert route.status_code == 201 and len(route.json()["stops"]) == 1
    assert client.post(f"/api/v1/routes/{route.json()['id']}/approve", headers=h["supervisor"]).json()["approved_by"]
    assert client.post(f"/api/v1/routes/{route.json()['id']}/approve", headers=h["supervisor"]).status_code == 400
    assert client.post(f"/api/v1/work-orders/{order['id']}/assign", headers=h["supervisor"], json={"worker_id": worker_id}).json()["status"] == "assigned"


    # The worker sees only their own order and moves it along.
    mine = client.get("/api/v1/work-orders", headers=h["worker"]).json()
    assert [o["id"] for o in mine] == [order["id"]]
    assert client.post(f"/api/v1/work-orders/{order['id']}/start", headers=h["worker"]).json()["status"] == "in_progress"
    assert client.get(f"/api/v1/incidents/{incident_id}", headers=h["worker"]).json()["status"] == "in_progress"
    assert client.post(f"/api/v1/work-orders/{order['id']}/complete", headers=h["worker"]).json()["status"] == "completed"

    # After photo: a copy of the before photo cannot auto-verify, a new one can.
    same = client.post(f"/api/v1/incidents/{incident_id}/verification", headers=h["worker"], files={"file": ("a.jpg", b"before-photo", "image/jpeg")})
    assert same.json()["status"] == "uncertain"
    good = client.post(f"/api/v1/incidents/{incident_id}/verification", headers=h["worker"], files={"file": ("b.jpg", b"clean-street", "image/jpeg")}, data={"notes": "all clear"})
    assert good.json()["status"] == "verified"
    assert client.get(f"/api/v1/incidents/{incident_id}", headers=h["resident"]).json()["status"] == "verified"

    # Photos are viewable; the timeline records who did what.
    media = client.get(f"/api/v1/incidents/{incident_id}/media", headers=h["resident"]).json()
    assert len(media) == 3
    assert client.get(f"/api/v1/media/{media[-1]['id']}/content", headers=h["resident"]).content
    actions = [e["action"] for e in client.get(f"/api/v1/incidents/{incident_id}/timeline", headers=h["supervisor"]).json()]
    assert {"created", "analyzed", "approved", "assigned", "started", "completed"} <= set(actions)

    # Supervisor can overturn the rule check, which sends the job back to the field.
    review = client.post(f"/api/v1/verification/{good.json()['id']}/review", headers=h["supervisor"], json={"status": "rejected", "reason": "Bags still visible"})
    assert review.json()["status"] == "rejected"
    assert client.get(f"/api/v1/incidents/{incident_id}", headers=h["supervisor"]).json()["status"] == "in_progress"
    assert client.get(f"/api/v1/work-orders/{order['id']}", headers=h["supervisor"]).json()["status"] == "in_progress"


def test_role_boundaries(world):
    client, h, worker_id, admin_id = world
    incident_id = report(client, h["resident"])

    # Reporters only see their own reports.
    assert client.get(f"/api/v1/incidents/{incident_id}", headers=h["other"]).status_code == 404
    assert client.get("/api/v1/incidents", headers=h["other"]).json() == []
    assert len(client.get("/api/v1/incidents", headers=h["resident"]).json()) == 1
    assert client.post(f"/api/v1/incidents/{incident_id}/media", headers=h["other"], files={"file": ("a.jpg", b"x", "image/jpeg")}).status_code == 404

    forbidden = [
        ("get", "/api/v1/queue", "resident"),
        ("get", "/api/v1/queue", "worker"),
        ("get", "/api/v1/users", "supervisor"),
        ("get", "/api/v1/audit", "worker"),
        ("get", "/api/v1/jobs", "supervisor"),
        ("get", "/api/v1/routes", "worker"),
        ("get", "/api/v1/pilots", "resident"),
        ("get", f"/api/v1/incidents/{incident_id}/risk", "resident"),
        ("post", f"/api/v1/incidents/{incident_id}/analysis", "resident"),
    ]
    for method, path, role in forbidden:
        assert getattr(client, method)(path, headers=h[role]).status_code == 403, (method, path, role)
    assert client.get("/api/v1/users?role=sanitation_worker", headers=h["supervisor"]).status_code == 200
    assert client.get("/api/v1/queue").status_code == 401

    # Only a worker can start work, only the supervisor can open orders.
    client.post(f"/api/v1/incidents/{incident_id}/analysis", headers=h["supervisor"])
    assert client.post(f"/api/v1/incidents/{incident_id}/work-orders", headers=h["worker"], json={"priority": 1}).status_code == 403
    order = client.post(f"/api/v1/incidents/{incident_id}/work-orders", headers=h["supervisor"], json={"priority": 1}).json()
    assert client.post(f"/api/v1/work-orders/{order['id']}/start", headers=h["supervisor"]).status_code == 403
    assert client.get(f"/api/v1/work-orders/{order['id']}", headers=h["worker"]).status_code == 404  # not theirs

    # Sidebar badges: each role sees the count of what is waiting for them.
    assert client.get("/api/v1/me/badges", headers=h["resident"]).json() == {"incidents": 1}
    assert client.get("/api/v1/me/badges", headers=h["supervisor"]).json() == {"incidents": 1, "work": 0, "routes": 0}
    assert client.get("/api/v1/me/badges", headers=h["worker"]).json() == {"work": 0}

    # Admins manage accounts, but never their own role.
    assert client.patch(f"/api/v1/users/{admin_id}", headers=h["admin"], json={"role": "reporter"}).status_code == 400
    assert client.patch(f"/api/v1/users/{worker_id}", headers=h["admin"], json={"is_active": False}).json()["is_active"] is False
    assert client.get("/api/v1/work-orders", headers=h["worker"]).status_code == 401  # deactivated mid-session


def test_admin_tools_pilots_sensors_municipal_and_jobs(world):
    client, h, worker_id, _ = world
    incident_id = report(client, h["resident"])
    client.post(f"/api/v1/incidents/{incident_id}/analysis", headers=h["supervisor"])
    order = client.post(f"/api/v1/incidents/{incident_id}/work-orders", headers=h["supervisor"], json={"priority": 3}).json()
    client.post(f"/api/v1/work-orders/{order['id']}/approve", headers=h["supervisor"])

    # Duplicates: a second nearby report shows up as a candidate.
    twin = report(client, h["other"], text="Overflowing bins near the market", lat=30.7334, lon=76.7795)
    found = client.get(f"/api/v1/incidents/{twin}/duplicates", headers=h["supervisor"]).json()
    assert [c["incident"]["id"] for c in found["candidates"]] == [incident_id]
    cluster = client.post(f"/api/v1/incidents/{twin}/duplicates/cluster", headers=h["supervisor"], json={"candidate_ids": [incident_id]}).json()
    assert client.post(f"/api/v1/duplicate-clusters/{cluster['id']}/confirm", headers=h["supervisor"]).json()["confirmed"] is True

    # Sensors, municipal exchange.
    reading = client.post("/api/v1/sensors/readings", headers=h["supervisor"], json={"sensor_id": "bin-9", "latitude": 30.7333, "longitude": 76.7794, "reading": {"fill_level": 0.9}}).json()
    assert client.post(f"/api/v1/sensors/readings/{reading['id']}/associate", headers=h["supervisor"], json={"incident_id": incident_id}).json()["incident_id"] == incident_id
    assert client.get("/api/v1/sensors/bin-9/latest", headers=h["supervisor"]).json()["reading"]["fill_level"] == 0.9
    exported = client.post("/api/v1/municipal/export", headers=h["supervisor"], json={"work_order_ids": [order["id"]], "system_name": "ward-office"}).json()
    assert exported["work_orders"][0]["id"] == order["id"]
    imported = client.post("/api/v1/municipal/import", headers=h["supervisor"], json={"updates": [{"work_order_id": order["id"], "status": "cancelled"}]}).json()
    assert imported["imported"] == 1

    # Evaluations and pilots.
    run = client.post("/api/v1/evaluations/run", headers=h["supervisor"], json={}).json()
    assert run["metrics"]["incidents_total"] == 2
    assert run["id"] in [r["id"] for r in client.get("/api/v1/evaluations", headers=h["supervisor"]).json()]
    pilot = client.post("/api/v1/pilots", headers=h["supervisor"], json={"name": "Chandigarh", "location": "Sector 17", "start_date": "2026-11-01", "end_date": "2027-01-10", "baseline_version": "q3-2026"})
    assert pilot.status_code == 201, pilot.text
    pid = pilot.json()["id"]
    assert pid in [p["id"] for p in client.get("/api/v1/pilots", headers=h["supervisor"]).json()]
    assert client.post(f"/api/v1/pilots/{pid}/metrics", headers=h["supervisor"], json={"metrics": {"resolution_hours": 18}}).json()["metrics"]["resolution_hours"] == 18
    assert client.post(f"/api/v1/pilots/{pid}/close", headers=h["supervisor"]).status_code == 200
    assert client.post("/api/v1/pilots", headers=h["supervisor"], json={"name": "x", "location": "y", "start_date": "2026-11-01", "end_date": "2026-11-05", "baseline_version": "v"}).status_code == 400

    # Background jobs run in-process and are visible to admins.
    queued = client.post(f"/api/v1/incidents/{twin}/analysis?async_mode=true", headers=h["supervisor"]).json()
    for _ in range(40):
        job = client.get(f"/api/v1/jobs/{queued['job_id']}", headers=h["supervisor"]).json()
        if job["status"] == "succeeded":
            break
        time.sleep(0.25)
    assert job["status"] == "succeeded" and job["result"]["risk_score"] > 0
    assert queued["job_id"] in [j["id"] for j in client.get("/api/v1/jobs", headers=h["admin"]).json()]
    assert client.get("/api/v1/audit", headers=h["admin"]).json()
    assert client.get("/api/v1/system/status", headers=h["worker"]).json()["worker"] == "in-process"
