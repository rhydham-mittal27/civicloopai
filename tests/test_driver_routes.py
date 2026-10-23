"""Routes belong to one driver: only that driver's assigned jobs can be grouped, and approving sends the route to them."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from civicloop.api import create_app
from civicloop.jobs import InMemoryJobQueue
from civicloop.storage import InMemoryObjectStorage

PASSWORD = "correct horse battery"


class FakeAdapter:
    provider = "test"
    model_name = "test-model"

    def analyze(self, payload):
        return {"category": "mixed_waste", "severity": "high", "confidence": 0.9, "details": {}}


@pytest.fixture()
def city(tmp_path):
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'routes.db'}",
        auth_secret="test-secret-that-is-at-least-32-characters",
        storage=InMemoryObjectStorage(),
        queue=InMemoryJobQueue(),
        analysis_adapter_factory=FakeAdapter,
    )
    with TestClient(app) as client:

        def make(role, email, headers=None, city="Chandigarh", pin="160017"):
            r = client.post("/api/v1/auth/register", headers=headers or {}, json={"name": email.split("@")[0], "email": email, "password": PASSWORD, "role": role, "city": city, "pincode": pin})
            assert r.status_code == 201, r.text
            token = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()["access_token"]
            return {"Authorization": f"Bearer {token}"}, r.json()["user_id"]

        admin, _ = make("admin", "admin@x.test")
        sup, _ = make("supervisor", "sup@x.test", admin)
        asha, asha_id = make("sanitation_worker", "asha@x.test", admin)
        ravi, ravi_id = make("sanitation_worker", "ravi@x.test", admin)
        resident, _ = make("reporter", "res@x.test")
        other_admin, _ = make("admin", "admin@pune.test", city="Pune", pin="411001")
        pune_worker, _ = make("sanitation_worker", "w@pune.test", other_admin, city="Pune", pin="411001")

        def job(label, lat, assign_to=None, approve=True):
            inc = client.post("/api/v1/incidents", headers=resident, json={"reporter_type": "resident", "description": label, "latitude": lat, "longitude": 76.77, "occurred_at": datetime.now(timezone.utc).isoformat()}).json()
            client.post(f"/api/v1/incidents/{inc['id']}/media", headers=resident, files={"file": ("a.jpg", b"\xff\xd8\xffx", "image/jpeg")})
            assert client.post(f"/api/v1/incidents/{inc['id']}/analysis", headers=sup).status_code == 200
            order = client.post(f"/api/v1/incidents/{inc['id']}/work-orders", headers=sup, json={"priority": 50, "estimated_volume": 1}).json()
            if approve:
                client.post(f"/api/v1/work-orders/{order['id']}/approve", headers=sup)
            if assign_to:
                assert client.post(f"/api/v1/work-orders/{order['id']}/assign", headers=sup, json={"worker_id": assign_to}).status_code == 200
            return order["id"]

        yield client, dict(sup=sup, asha=asha, ravi=ravi, resident=resident, pune=pune_worker, asha_id=asha_id, ravi_id=ravi_id), job


def plan(client, headers, ids):
    return client.post("/api/v1/routes", headers=headers, json={"work_order_ids": ids, "vehicle_capacity": 10})


def test_only_jobs_already_assigned_to_a_driver_can_be_routed(city):
    client, w, job = city
    unassigned = job("Not assigned yet", 30.70)
    r = plan(client, w["sup"], [unassigned])
    assert r.status_code == 400 and "assigned" in r.json()["detail"].lower()
    assert client.post("/api/v1/routes/preview", headers=w["sup"], json={"work_order_ids": [unassigned], "vehicle_capacity": 10}).status_code == 400
    assert plan(client, w["sup"], []).status_code == 422 or plan(client, w["sup"], []).status_code == 400


def test_a_route_cannot_mix_drivers(city):
    client, w, job = city
    a = job("Asha 1", 30.70, w["asha_id"])
    b = job("Ravi 1", 30.71, w["ravi_id"])
    r = plan(client, w["sup"], [a, b])
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "same driver" in detail and "asha" in detail and "ravi" in detail
    assert client.post("/api/v1/routes/preview", headers=w["sup"], json={"work_order_ids": [a, b], "vehicle_capacity": 10}).status_code == 400


def test_a_route_for_one_driver_names_the_driver_and_is_hidden_until_approved(city):
    client, w, job = city
    ids = [job(f"Asha {i}", 30.70 + i * 0.01, w["asha_id"]) for i in range(3)]
    made = plan(client, w["sup"], ids)
    assert made.status_code == 201, made.text
    route = made.json()
    assert route["worker_id"] == w["asha_id"] and route["worker_name"] == "asha"
    preview = client.post("/api/v1/routes/preview", headers=w["sup"], json={"work_order_ids": ids, "vehicle_capacity": 10}).json()
    assert preview["worker_name"] == "asha"

    # a draft is the supervisor's: the driver cannot see it, by list or by address
    assert client.get("/api/v1/routes/mine", headers=w["asha"]).json() == []
    assert client.get(f"/api/v1/routes/{route['id']}", headers=w["asha"]).status_code == 404

    approved = client.post(f"/api/v1/routes/{route['id']}/approve", headers=w["sup"]).json()
    assert approved["approved_at"] and approved["active"] is True

    # approving sent it to that driver, and only that driver
    mine = client.get("/api/v1/routes/mine", headers=w["asha"]).json()
    assert [r["id"] for r in mine] == [route["id"]]
    assert [s["sequence"] for s in mine[0]["stops"]] == [0, 1, 2] and mine[0]["next_stop"] == 0
    assert client.get(f"/api/v1/routes/{route['id']}", headers=w["asha"]).status_code == 200
    assert client.get("/api/v1/routes/mine", headers=w["ravi"]).json() == []
    assert client.get(f"/api/v1/routes/{route['id']}", headers=w["ravi"]).status_code == 404
    assert client.get("/api/v1/me/badges", headers=w["asha"]).json()["routes"] == 1
    assert client.get("/api/v1/me/badges", headers=w["ravi"]).json()["routes"] == 0


def test_the_driver_never_gets_supervisor_route_tools(city):
    client, w, job = city
    ids = [job("Asha", 30.70, w["asha_id"])]
    route = plan(client, w["sup"], ids).json()
    assert client.get("/api/v1/routes", headers=w["asha"]).status_code == 403
    assert plan(client, w["asha"], ids).status_code == 403
    assert client.post(f"/api/v1/routes/{route['id']}/approve", headers=w["asha"]).status_code == 403
    assert client.get("/api/v1/routes/mine", headers=w["sup"]).status_code == 403
    assert client.get("/api/v1/routes/mine", headers=w["resident"]).status_code == 403


def test_progress_follows_the_drivers_jobs(city):
    client, w, job = city
    ids = [job(f"Stop {i}", 30.70 + i * 0.01, w["asha_id"]) for i in range(3)]
    route = plan(client, w["sup"], ids).json()
    client.post(f"/api/v1/routes/{route['id']}/approve", headers=w["sup"])
    first = route["stops"][0]["work_order_id"]

    client.post(f"/api/v1/work-orders/{first}/start", headers=w["asha"])
    started = client.get("/api/v1/routes/mine", headers=w["asha"]).json()[0]
    assert (started["stops_done"], started["next_stop"]) == (0, 0)  # started, not finished

    client.post(f"/api/v1/work-orders/{first}/complete", headers=w["asha"])
    mine = client.get("/api/v1/routes/mine", headers=w["asha"]).json()[0]
    assert (mine["stops_done"], mine["stops_total"], mine["next_stop"]) == (1, 3, 1)
    assert mine["stops"][0]["done"] is True and mine["active"] is True

    for stop in route["stops"][1:]:
        client.post(f"/api/v1/work-orders/{stop['work_order_id']}/start", headers=w["asha"])
        client.post(f"/api/v1/work-orders/{stop['work_order_id']}/complete", headers=w["asha"])
    finished = client.get("/api/v1/routes/mine", headers=w["asha"]).json()[0]
    assert (finished["stops_done"], finished["next_stop"], finished["active"]) == (3, None, False)
    assert client.get("/api/v1/me/badges", headers=w["asha"]).json()["routes"] == 0  # nothing left to do


def test_a_stale_route_cannot_be_approved_and_a_job_is_on_one_approved_route(city):
    client, w, job = city
    a, b = job("A", 30.70, w["asha_id"]), job("B", 30.71, w["asha_id"])
    first = plan(client, w["sup"], [a, b]).json()
    second = plan(client, w["sup"], [b]).json()
    assert client.post(f"/api/v1/routes/{first['id']}/approve", headers=w["sup"]).status_code == 200
    clash = client.post(f"/api/v1/routes/{second['id']}/approve", headers=w["sup"])
    assert clash.status_code == 400 and "already on another approved route" in clash.json()["detail"]

    # a job finished between planning and approving: the plan is out of date
    c = job("C", 30.72, w["asha_id"])
    draft = plan(client, w["sup"], [c]).json()
    client.post(f"/api/v1/work-orders/{c}/start", headers=w["asha"])
    client.post(f"/api/v1/work-orders/{c}/complete", headers=w["asha"])
    stale = client.post(f"/api/v1/routes/{draft['id']}/approve", headers=w["sup"])
    assert stale.status_code == 400 and "plan the route again" in stale.json()["detail"].lower()


def test_another_citys_people_cannot_reach_a_route(city):
    client, w, job = city
    route = plan(client, w["sup"], [job("Asha", 30.70, w["asha_id"])]).json()
    client.post(f"/api/v1/routes/{route['id']}/approve", headers=w["sup"])
    assert client.get(f"/api/v1/routes/{route['id']}", headers=w["pune"]).status_code == 404
    assert client.get("/api/v1/routes/mine", headers=w["pune"]).json() == []
