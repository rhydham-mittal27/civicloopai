"""Live vehicle tracking: GPS from a phone or a tracker, plausibility checks, roles and city isolation."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from civicloop.api import create_app
from civicloop.jobs import InMemoryJobQueue
from civicloop.storage import InMemoryObjectStorage

PASSWORD = "correct horse battery"
CITY = {"a": ("Chandigarh", "160017"), "b": ("Pune", "411001")}


def iso(delta_seconds: float = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=delta_seconds)).isoformat()


@pytest.fixture()
def fleet(tmp_path):
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'fleet.db'}",
        auth_secret="test-secret-that-is-at-least-32-characters",
        storage=InMemoryObjectStorage(),
        queue=InMemoryJobQueue(),
    )
    with TestClient(app) as client:

        def make(role, email, key, headers=None):
            city, pin = CITY[key]
            r = client.post("/api/v1/auth/register", headers=headers or {}, json={"name": role, "email": email, "password": PASSWORD, "role": role, "city": city, "pincode": pin})
            assert r.status_code == 201, r.text
            token = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()["access_token"]
            return {"Authorization": f"Bearer {token}"}, r.json()["user_id"]

        world = {}
        for key in ("a", "b"):
            admin, _ = make("admin", f"admin-{key}@x.test", key)
            sup, _ = make("supervisor", f"sup-{key}@x.test", key, admin)
            worker, worker_id = make("sanitation_worker", f"w-{key}@x.test", key, admin)
            other, other_id = make("sanitation_worker", f"w2-{key}@x.test", key, admin)
            resident, _ = make("reporter", f"res-{key}@x.test", key)
            world[key] = dict(admin=admin, sup=sup, worker=worker, worker_id=worker_id, other=other, other_id=other_id, resident=resident)
        yield client, world


def add_vehicle(client, w, label="Truck 1", driver="worker_id"):
    r = client.post("/api/v1/vehicles", headers=w["sup"], json={"label": label, "registration": "ch01 ab 1234", "driver_id": w[driver] if driver else None})
    assert r.status_code == 201, r.text
    return r.json()


def test_a_supervisor_registers_a_vehicle_and_gets_the_tracker_key_once(fleet):
    client, world = fleet
    v = add_vehicle(client, world["a"])
    assert v["device_key"].startswith("clv_") and v["registration"] == "CH01 AB 1234"
    assert v["state"] == "no_signal" and v["lat"] is None
    listed = client.get("/api/v1/vehicles", headers=world["a"]["sup"]).json()
    assert [x["label"] for x in listed] == ["Truck 1"] and "device_key" not in listed[0]
    assert listed[0]["driver_name"] == "sanitation_worker"


def test_only_supervisors_manage_and_read_the_fleet(fleet):
    client, world = fleet
    w = world["a"]
    v = add_vehicle(client, w)
    for who in ("worker", "resident"):
        assert client.get("/api/v1/vehicles", headers=w[who]).status_code == 403
        assert client.post("/api/v1/vehicles", headers=w[who], json={"label": "x"}).status_code == 403
        assert client.get(f"/api/v1/vehicles/{v['id']}/trail", headers=w[who]).status_code == 403
    assert client.get("/api/v1/vehicles/mine", headers=w["sup"]).status_code == 403
    assert client.post("/api/v1/vehicles/" + v["id"] + "/position", headers=w["resident"], json={"lat": 30.7, "lon": 76.8}).status_code == 403


def test_the_driver_phone_moves_the_vehicle_on_the_map(fleet):
    client, world = fleet
    w = world["a"]
    v = add_vehicle(client, w)
    mine = client.get("/api/v1/vehicles/mine", headers=w["worker"]).json()
    assert [x["id"] for x in mine] == [v["id"]]
    assert client.get("/api/v1/vehicles/mine", headers=w["other"]).json() == []

    r = client.post(f"/api/v1/vehicles/{v['id']}/position", headers=w["worker"], json={"lat": 30.7333, "lon": 76.7794, "speed_kmh": 22, "heading": 90, "accuracy_m": 8})
    assert r.status_code == 200 and r.json() == {"accepted": 1, "dropped": 0}
    now = client.get("/api/v1/vehicles", headers=w["sup"]).json()[0]
    assert (now["lat"], now["lon"], now["state"], now["source"]) == (30.7333, 76.7794, "moving", "phone")
    assert now["speed_kmh"] == 22 and now["age_seconds"] < 30

    # a worker cannot report for someone else's vehicle
    assert client.post(f"/api/v1/vehicles/{v['id']}/position", headers=w["other"], json={"lat": 30.7, "lon": 76.7}).status_code == 403


def test_a_tracker_reports_with_its_key_and_cannot_use_a_wrong_one(fleet):
    client, world = fleet
    w = world["a"]
    v = add_vehicle(client, w)
    key = {"X-Device-Key": v["device_key"]}
    assert client.post("/api/v1/telemetry/gps", json={"lat": 30.74, "lon": 76.78}).status_code == 401
    assert client.post("/api/v1/telemetry/gps", headers={"X-Device-Key": "clv_nope"}, json={"lat": 30.74, "lon": 76.78}).status_code == 401
    ok = client.post("/api/v1/telemetry/gps", headers=key, json={"lat": 30.74, "lon": 76.78, "speed_kmh": 0})
    assert ok.status_code == 200 and ok.json()["accepted"] == 1
    now = client.get("/api/v1/vehicles", headers=w["sup"]).json()[0]
    assert now["source"] == "device" and now["state"] == "idle"
    # nothing to send
    assert client.post("/api/v1/telemetry/gps", headers=key, json={}).status_code == 422


def test_a_buffered_batch_is_stored_in_order_and_the_latest_wins(fleet):
    client, world = fleet
    w = world["a"]
    v = add_vehicle(client, w)
    key = {"X-Device-Key": v["device_key"]}
    points = [
        {"lat": 30.7400, "lon": 76.7800, "recorded_at": iso(-60)},
        {"lat": 30.7380, "lon": 76.7790, "recorded_at": iso(-120)},  # arrives out of order
        {"lat": 30.7420, "lon": 76.7810, "recorded_at": iso(-10)},
    ]
    assert client.post("/api/v1/telemetry/gps", headers=key, json={"points": points}).json() == {"accepted": 3, "dropped": 0}
    now = client.get("/api/v1/vehicles", headers=w["sup"]).json()[0]
    assert (now["lat"], now["lon"]) == (30.7420, 76.7810)
    trail = client.get(f"/api/v1/vehicles/{v['id']}/trail?minutes=10", headers=w["sup"]).json()
    assert [round(p["lat"], 4) for p in trail] == [30.738, 30.74, 30.742]
    # a late fix older than what we already have does not drag the vehicle back
    client.post("/api/v1/telemetry/gps", headers=key, json={"lat": 30.5, "lon": 76.5, "recorded_at": iso(-200)})
    assert client.get("/api/v1/vehicles", headers=w["sup"]).json()[0]["lat"] == 30.742


def test_glitches_and_bad_timestamps_are_dropped(fleet):
    client, world = fleet
    w = world["a"]
    v = add_vehicle(client, w)
    key = {"X-Device-Key": v["device_key"]}
    client.post("/api/v1/telemetry/gps", headers=key, json={"lat": 30.7333, "lon": 76.7794, "recorded_at": iso(-30)})
    # 40 km away ten seconds later: impossible for a truck
    jump = client.post("/api/v1/telemetry/gps", headers=key, json={"lat": 31.1, "lon": 76.7794, "recorded_at": iso(-20)})
    assert jump.json() == {"accepted": 0, "dropped": 1}
    future = client.post("/api/v1/telemetry/gps", headers=key, json={"lat": 30.734, "lon": 76.78, "recorded_at": iso(3600)})
    assert future.json()["dropped"] == 1
    old = client.post("/api/v1/telemetry/gps", headers=key, json={"lat": 30.734, "lon": 76.78, "recorded_at": iso(-3 * 24 * 3600)})
    assert old.json()["dropped"] == 1
    vague = client.post("/api/v1/telemetry/gps", headers=key, json={"lat": 30.7335, "lon": 76.7795, "accuracy_m": 900})
    assert vague.json()["dropped"] == 1
    assert client.post("/api/v1/telemetry/gps", headers=key, json={"lat": 120, "lon": 76}).status_code == 422
    assert client.get("/api/v1/vehicles", headers=w["sup"]).json()[0]["lat"] == 30.7333


def test_speed_and_distance_are_worked_out_when_the_tracker_sends_only_position(fleet):
    client, world = fleet
    w = world["a"]
    v = add_vehicle(client, w)
    key = {"X-Device-Key": v["device_key"]}
    # about 1.1 km north in 2 minutes = about 33 km/h
    client.post("/api/v1/telemetry/gps", headers=key, json={"lat": 30.7000, "lon": 76.8000, "recorded_at": iso(-130)})
    client.post("/api/v1/telemetry/gps", headers=key, json={"lat": 30.7100, "lon": 76.8000, "recorded_at": iso(-10)})
    now = client.get("/api/v1/vehicles", headers=w["sup"]).json()[0]
    assert 25 < now["speed_kmh"] < 40
    assert 1.0 < now["distance_today_km"] < 1.3


def test_a_vehicle_goes_stale_then_offline_as_fixes_age(fleet):
    client, world = fleet
    w = world["a"]
    v = add_vehicle(client, w)
    key = {"X-Device-Key": v["device_key"]}
    client.post("/api/v1/telemetry/gps", headers=key, json={"lat": 30.7, "lon": 76.8, "speed_kmh": 20, "recorded_at": iso(-5 * 60)})
    assert client.get("/api/v1/vehicles", headers=w["sup"]).json()[0]["state"] == "stale"
    v2 = add_vehicle(client, w, "Truck 2", driver=None)
    client.post("/api/v1/telemetry/gps", headers={"X-Device-Key": v2["device_key"]}, json={"lat": 30.7, "lon": 76.8, "speed_kmh": 20, "recorded_at": iso(-30 * 60)})
    states = {x["label"]: x["state"] for x in client.get("/api/v1/vehicles", headers=w["sup"]).json()}
    assert states == {"Truck 1": "stale", "Truck 2": "offline"}


def test_rotating_the_key_cuts_off_the_old_tracker_and_switching_off_blocks_everything(fleet):
    client, world = fleet
    w = world["a"]
    v = add_vehicle(client, w)
    old = {"X-Device-Key": v["device_key"]}
    new = client.post(f"/api/v1/vehicles/{v['id']}/device-key", headers=w["sup"]).json()["device_key"]
    assert new != v["device_key"]
    assert client.post("/api/v1/telemetry/gps", headers=old, json={"lat": 30.7, "lon": 76.8}).status_code == 401
    assert client.post("/api/v1/telemetry/gps", headers={"X-Device-Key": new}, json={"lat": 30.7, "lon": 76.8}).status_code == 200
    off = client.patch(f"/api/v1/vehicles/{v['id']}", headers=w["sup"], json={"is_active": False}).json()
    assert off["state"] == "disabled"
    assert client.post("/api/v1/telemetry/gps", headers={"X-Device-Key": new}, json={"lat": 30.7, "lon": 76.8}).status_code == 401
    assert client.post(f"/api/v1/vehicles/{v['id']}/position", headers=w["worker"], json={"lat": 30.7, "lon": 76.8}).status_code == 409
    assert client.get("/api/v1/vehicles/mine", headers=w["worker"]).json() == []


def test_a_driver_must_be_a_worker_in_the_same_city(fleet):
    client, world = fleet
    a, b = world["a"], world["b"]
    bad = client.post("/api/v1/vehicles", headers=a["sup"], json={"label": "T", "driver_id": b["worker_id"]})
    assert bad.status_code == 409
    res = client.get("/api/v1/auth/me", headers=a["resident"]).json()
    assert client.post("/api/v1/vehicles", headers=a["sup"], json={"label": "T", "driver_id": res["id"]}).status_code == 409


def test_vehicles_and_positions_stay_inside_their_city(fleet):
    client, world = fleet
    a, b = world["a"], world["b"]
    v = add_vehicle(client, a)
    client.post("/api/v1/telemetry/gps", headers={"X-Device-Key": v["device_key"]}, json={"lat": 30.7, "lon": 76.8})
    assert client.get("/api/v1/vehicles", headers=b["sup"]).json() == []
    assert client.get(f"/api/v1/vehicles/{v['id']}/trail", headers=b["sup"]).status_code == 404
    assert client.patch(f"/api/v1/vehicles/{v['id']}", headers=b["sup"], json={"label": "hijack"}).status_code == 404
    assert client.post(f"/api/v1/vehicles/{v['id']}/device-key", headers=b["sup"]).status_code == 404
    assert client.post(f"/api/v1/vehicles/{v['id']}/position", headers=b["worker"], json={"lat": 30.7, "lon": 76.8}).status_code == 404
    # the tracker wrote into city A, not into any city of the sender's choosing
    assert len(client.get("/api/v1/vehicles", headers=a["sup"]).json()) == 1
