"""Multi-tenancy: two cities share one deployment and never see each other's data."""

import time
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
def cities(tmp_path):
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'tenants.db'}",
        auth_secret="test-secret-that-is-at-least-32-characters",
        storage=InMemoryObjectStorage(),
        queue=InMemoryJobQueue(),
        analysis_adapter_factory=FakeAdapter,
    )
    with TestClient(app) as client:

        def make(role, email, city, pincode, headers=None):
            r = client.post(
                "/api/v1/auth/register",
                headers=headers or {},
                json={"name": role, "email": email, "password": PASSWORD, "role": role, "city": city, "pincode": pincode},
            )
            assert r.status_code == 201, r.text
            token = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()["access_token"]
            return {"Authorization": f"Bearer {token}"}

        world = {}
        for key, city, pin in (("a", "Chandigarh", "160017"), ("b", "Pune", "411001")):
            admin = make("admin", f"admin-{key}@x.test", city, pin)
            world[key] = dict(
                admin=admin,
                supervisor=make("supervisor", f"sup-{key}@x.test", city, pin, admin),
                resident=make("reporter", f"res-{key}@x.test", city, pin),
            )
        yield client, world


def report(client, headers, text="Overflowing bins near the market", pincode=None):
    body = {
        "reporter_type": "resident",
        "description": text,
        "latitude": 30.73,
        "longitude": 76.77,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }
    if pincode:
        body["pincode"] = pincode
    r = client.post("/api/v1/incidents", headers=headers, json=body)
    assert r.status_code == 201, r.text
    incident = r.json()
    up = client.post(f"/api/v1/incidents/{incident['id']}/media", headers=headers, files={"file": ("a.jpg", b"\xff\xd8\xffphoto", "image/jpeg")})
    assert up.status_code == 201, up.text
    return incident


def test_registration_creates_the_city_and_records_the_pincode(cities):
    client, w = cities
    me = client.get("/api/v1/auth/me", headers=w["b"]["resident"]).json()
    assert (me["city"], me["pincode"]) == ("Pune", "411001")
    # self-opened cities are not suggested to strangers until a platform admin verifies them
    assert client.get("/api/v1/tenants?q=pu").json() == []


def test_city_names_are_matched_loosely(cities):
    client, _ = cities
    r = client.post("/api/v1/auth/register", json={"name": "N", "email": "n@x.test", "password": PASSWORD, "city": "  chandigarh ", "pincode": "160022"})
    assert r.status_code == 201 and r.json()["city"] == "Chandigarh"
    assert client.get("/api/v1/tenants").json() == []  # a lookup needs a few letters


@pytest.mark.parametrize("pincode", ["12345", "012345", "16001a", "1600177"])
def test_bad_pincodes_are_refused(cities, pincode):
    client, _ = cities
    r = client.post("/api/v1/auth/register", json={"name": "N", "email": "bad@x.test", "password": PASSWORD, "city": "Pune", "pincode": pincode})
    assert r.status_code in (400, 422)


def test_city_is_required(cities):
    client, _ = cities
    r = client.post("/api/v1/auth/register", json={"name": "N", "email": "nc@x.test", "password": PASSWORD, "pincode": "160017"})
    assert r.status_code == 422


def test_only_a_city_admin_can_promote_people(cities):
    client, w = cities
    body = {"name": "H", "email": "h@x.test", "password": PASSWORD, "role": "admin", "city": "Pune", "pincode": "411001"}
    assert client.post("/api/v1/auth/register", json=body).status_code == 403
    # another city's admin cannot add a supervisor to Pune by naming it
    r = client.post("/api/v1/auth/register", headers=w["a"]["admin"], json={**body, "email": "s@x.test", "role": "supervisor"})
    assert r.status_code == 201 and r.json()["city"] == "Chandigarh"
    # a brand-new city is administered by whoever opens it
    opened = client.post("/api/v1/auth/register", json={**body, "email": "new@x.test", "city": "Jaipur", "pincode": "302001"})
    assert opened.status_code == 201


def test_incidents_are_invisible_across_cities(cities):
    client, w = cities
    mine = report(client, w["a"]["resident"], pincode="160022")
    assert mine["pincode"] == "160022"
    assert report(client, w["a"]["resident"])["pincode"] == "160017"  # falls back to the reporter's own

    for who in ("supervisor", "admin", "resident"):
        assert client.get(f"/api/v1/incidents/{mine['id']}", headers=w["b"][who]).status_code == 404
        assert client.get("/api/v1/incidents", headers=w["b"][who]).json() == []
    assert len(client.get("/api/v1/incidents", headers=w["a"]["supervisor"]).json()) == 2
    by_pin = client.get("/api/v1/incidents?pincode=160022", headers=w["a"]["supervisor"]).json()
    assert [i["id"] for i in by_pin] == [mine["id"]]

    for path in ("analysis", "risk", "timeline", "duplicates", "work-orders", "media", "verification"):
        assert client.get(f"/api/v1/incidents/{mine['id']}/{path}", headers=w["b"]["supervisor"]).status_code == 404, path
    assert client.post(f"/api/v1/incidents/{mine['id']}/analysis", headers=w["b"]["supervisor"]).status_code == 404
    assert client.post(f"/api/v1/incidents/{mine['id']}/work-orders", headers=w["b"]["supervisor"], json={"priority": 5}).status_code == 404


def test_operations_data_is_per_city(cities):
    client, w = cities
    incident = report(client, w["a"]["resident"])
    assert client.post(f"/api/v1/incidents/{incident['id']}/analysis", headers=w["a"]["supervisor"]).status_code == 200
    order = client.post(f"/api/v1/incidents/{incident['id']}/work-orders", headers=w["a"]["supervisor"], json={"priority": 5}).json()

    other = w["b"]["supervisor"]
    assert client.get("/api/v1/work-orders", headers=other).json() == []
    assert client.post(f"/api/v1/work-orders/{order['id']}/approve", headers=other).status_code == 404
    assert client.get("/api/v1/queue", headers=other).json() == []
    assert client.get("/api/v1/dashboard/map", headers=other).json() == []
    events = client.get("/api/v1/audit", headers=w["b"]["admin"]).json()
    assert all(e["entity_id"] != incident["id"] for e in events)
    assert client.get("/api/v1/dashboard/map", headers=w["a"]["supervisor"]).json()


def test_people_and_jobs_are_per_city(cities):
    client, w = cities
    emails = {u["email"] for u in client.get("/api/v1/users", headers=w["b"]["admin"]).json()}
    assert emails == {"admin-b@x.test", "sup-b@x.test", "res-b@x.test"}
    a_user = next(u for u in client.get("/api/v1/users", headers=w["a"]["admin"]).json() if u["email"] == "res-a@x.test")
    assert client.patch(f"/api/v1/users/{a_user['id']}", headers=w["b"]["admin"], json={"is_active": False}).status_code == 404

    incident = report(client, w["a"]["resident"])
    queued = client.post(f"/api/v1/incidents/{incident['id']}/analysis?async_mode=true", headers=w["a"]["supervisor"])
    job_id = queued.json()["job_id"]
    assert client.get(f"/api/v1/jobs/{job_id}", headers=w["b"]["admin"]).status_code in (403, 404)
    assert all(j["id"] != job_id for j in client.get("/api/v1/jobs", headers=w["b"]["admin"]).json())
    assert client.post(f"/api/v1/jobs/{job_id}/cancel", headers=w["b"]["admin"]).status_code == 404


def test_media_cannot_be_fetched_across_cities(cities):
    client, w = cities
    incident = report(client, w["a"]["resident"])
    asset = client.get(f"/api/v1/incidents/{incident['id']}/media", headers=w["a"]["resident"]).json()[0]
    assert asset["storage_key"].startswith("tenants/")
    assert client.get(f"/api/v1/media/{asset['id']}/content", headers=w["a"]["resident"]).status_code == 200
    assert client.get(f"/api/v1/media/{asset['id']}/content", headers=w["b"]["supervisor"]).status_code == 404


def test_background_jobs_stay_in_their_city(cities):
    client, w = cities
    a = report(client, w["a"]["resident"], "Pile of garbage at the bus stop")
    b = report(client, w["b"]["resident"], "Pile of garbage at the bus stop")
    for incident, who in ((a, w["a"]), (b, w["b"])):
        client.post(f"/api/v1/incidents/{incident['id']}/analysis?async_mode=true", headers=who["supervisor"])
    done = []
    for _ in range(60):
        done = [client.get(f"/api/v1/incidents/{i['id']}", headers=who["supervisor"]).json()["status"] for i, who in ((a, w["a"]), (b, w["b"]))]
        if all(s == "ready_for_review" for s in done):
            break
        time.sleep(0.25)
    assert done == ["ready_for_review"] * 2
    # an identical report in the other city is never offered as a duplicate
    for incident, who in ((a, w["a"]), (b, w["b"])):
        found = client.get(f"/api/v1/incidents/{incident['id']}/duplicates", headers=who["supervisor"]).json()
        assert found["candidates"] == []


@pytest.fixture()
def platform(cities, monkeypatch):
    monkeypatch.setenv("CIVICLOOP_PLATFORM_ADMINS", "admin-a@x.test")
    client, w = cities
    return client, w, w["a"]["admin"]


def test_only_a_platform_admin_reaches_the_platform_routes(platform):
    client, w, root = platform
    assert client.get("/api/v1/platform/cities", headers=w["b"]["admin"]).status_code == 403
    assert client.get("/api/v1/platform/cities", headers=w["a"]["supervisor"]).status_code == 403
    rows = client.get("/api/v1/platform/cities", headers=root).json()
    assert {r["name"]: (r["users"], r["verified"]) for r in rows} == {"Chandigarh": (3, False), "Pune": (3, False)}
    me = client.get("/api/v1/auth/me", headers=root).json()
    assert me["is_platform_admin"] is True
    assert client.get("/api/v1/auth/me", headers=w["b"]["admin"]).json()["is_platform_admin"] is False


def test_verified_cities_are_suggested_and_unverified_ones_are_not(platform):
    client, w, root = platform
    pune = next(r for r in client.get("/api/v1/platform/cities", headers=root).json() if r["name"] == "Pune")
    assert client.patch(f"/api/v1/platform/cities/{pune['id']}", headers=root, json={"verified": True}).json()["verified"] is True
    assert [t["name"] for t in client.get("/api/v1/tenants?q=pu").json()] == ["Pune"]
    assert client.get("/api/v1/tenants?q=p").json() == []


def test_a_platform_admin_can_step_into_another_city(platform):
    client, w, root = platform
    mine = report(client, w["b"]["resident"])
    pune = next(r for r in client.get("/api/v1/platform/cities", headers=root).json() if r["name"] == "Pune")
    assert client.get(f"/api/v1/incidents/{mine['id']}", headers=root).status_code == 404
    inside = {**root, "X-Tenant-Id": pune["id"]}
    assert client.get(f"/api/v1/incidents/{mine['id']}", headers=inside).status_code == 200
    assert client.get("/api/v1/auth/me", headers=inside).json()["city"] == "Pune"
    # what they do there is recorded in that city
    assert client.post(f"/api/v1/incidents/{mine['id']}/analysis", headers=inside).status_code == 200
    assert any(e["entity_id"] == mine["id"] for e in client.get("/api/v1/audit", headers=w["b"]["admin"]).json())
    # nobody else may
    assert client.get("/api/v1/incidents", headers={**w["a"]["supervisor"], "X-Tenant-Id": pune["id"]}).status_code == 403


def test_a_misspelt_city_can_be_merged_into_the_real_one(platform):
    client, w, root = platform
    typo = client.post("/api/v1/auth/register", json={"name": "T", "email": "t@x.test", "password": PASSWORD, "city": "Punee", "pincode": "411002"})
    assert typo.status_code == 201 and typo.json()["city_verified"] is False
    rows = {r["name"]: r for r in client.get("/api/v1/platform/cities", headers=root).json()}
    # a city still in use cannot be merged: switch it off first so nothing is written while its records move
    live = client.post(f"/api/v1/platform/cities/{rows['Punee']['id']}/merge", headers=root, json={"into_id": rows["Pune"]["id"]})
    assert live.status_code == 409 and "Disable the city first" in live.json()["detail"]
    assert client.patch(f"/api/v1/platform/cities/{rows['Punee']['id']}", headers=root, json={"is_active": False}).status_code == 200
    merged = client.post(f"/api/v1/platform/cities/{rows['Punee']['id']}/merge", headers=root, json={"into_id": rows["Pune"]["id"]})
    assert merged.status_code == 200 and merged.json()["users"] == 4
    assert "Punee" not in {r["name"] for r in client.get("/api/v1/platform/cities", headers=root).json()}
    token = client.post("/api/v1/auth/login", json={"email": "t@x.test", "password": PASSWORD}).json()["access_token"]
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["city"] == "Pune"
    assert client.post(f"/api/v1/platform/cities/{rows['Pune']['id']}/merge", headers=root, json={"into_id": rows["Pune"]["id"]}).status_code == 400


def test_disabling_a_city_locks_its_people_out(platform):
    client, w, root = platform
    pune = next(r for r in client.get("/api/v1/platform/cities", headers=root).json() if r["name"] == "Pune")
    assert client.patch(f"/api/v1/platform/cities/{pune['id']}", headers=root, json={"is_active": False}).status_code == 200
    assert client.get("/api/v1/incidents", headers=w["b"]["resident"]).status_code == 401
    assert client.get("/api/v1/incidents", headers=w["a"]["resident"]).status_code == 200
    own = next(r for r in client.get("/api/v1/platform/cities", headers=root).json() if r["name"] == "Chandigarh")
    assert client.patch(f"/api/v1/platform/cities/{own['id']}", headers=root, json={"is_active": False}).status_code == 400


def test_a_city_is_never_left_without_an_administrator(platform):
    client, w, root = platform
    pune = next(r for r in client.get("/api/v1/platform/cities", headers=root).json() if r["name"] == "Pune")
    inside = {**root, "X-Tenant-Id": pune["id"]}
    admins = [u for u in client.get("/api/v1/users", headers=inside).json() if u["role"] == "admin"]
    assert len(admins) == 1
    for change in ({"role": "reporter"}, {"is_active": False}):
        refused = client.patch(f"/api/v1/users/{admins[0]['id']}", headers=inside, json=change)
        assert refused.status_code == 400 and "at least one active administrator" in refused.json()["detail"]
