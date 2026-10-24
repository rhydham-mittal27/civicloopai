"""The reliability and security fixes from docs/FMEA.md, one behaviour at a time."""

import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from civicloop.api import create_app
from civicloop.auth import hash_password, verify_password
from civicloop.db import create_engine, create_session_factory, init_db
from civicloop.jobs import InMemoryJobQueue, JobDelivery, JobWorker, utc_now
from civicloop.models import Incident, Job, JobStatus, ReporterType, User, UserRole, WorkOrder, WorkOrderStatus
from civicloop.repositories import JobRepository
from civicloop.storage import InMemoryObjectStorage
from civicloop.tenancy import bind_tenant, lift_scope
from civicloop.worker import recover_jobs

PASSWORD = "correct horse battery"
JPEG = b"\xff\xd8\xff\xe0" + b"photo"
SECRET = "test-secret-that-is-at-least-32-characters"


class FakeAdapter:
    provider = "test"
    model_name = "test-model"

    def analyze(self, payload):
        return {"category": "mixed_waste", "severity": "high", "confidence": 0.9, "details": {}}


def build(tmp_path, **kwargs):
    return create_app(
        database_url=f"sqlite:///{tmp_path / 'h.db'}",
        auth_secret=SECRET,
        storage=InMemoryObjectStorage(),
        queue=InMemoryJobQueue(),
        analysis_adapter_factory=FakeAdapter,
        **kwargs,
    )


@pytest.fixture()
def world(tmp_path):
    with TestClient(build(tmp_path)) as client:

        def make(role, email, headers=None, city="Chandigarh", pin="160017"):
            r = client.post("/api/v1/auth/register", headers=headers or {}, json={"name": email.split("@")[0], "email": email, "password": PASSWORD, "role": role, "city": city, "pincode": pin})
            assert r.status_code == 201, r.text
            token = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()["access_token"]
            return {"Authorization": f"Bearer {token}"}, r.json()["user_id"]

        admin, _ = make("admin", "admin@x.test")
        sup, _ = make("supervisor", "sup@x.test", admin)
        worker, worker_id = make("sanitation_worker", "w@x.test", admin)
        resident, _ = make("reporter", "res@x.test")
        yield client, dict(admin=admin, sup=sup, worker=worker, worker_id=worker_id, resident=resident), make


def report(client, headers, key=None, **over):
    body = {"reporter_type": "resident", "description": "Bins overflowing", "latitude": 30.7, "longitude": 76.77, "occurred_at": datetime.now(timezone.utc).isoformat(), **over}
    return client.post("/api/v1/incidents", headers={**headers, **({"Idempotency-Key": key} if key else {})}, json=body)


# ------------------------------------------------------------------ F-01, F-15, F-37 sign-in


def test_repeated_wrong_passwords_are_throttled_then_cleared_by_success(tmp_path, monkeypatch):
    monkeypatch.setenv("CIVICLOOP_LOGIN_ATTEMPTS", "3")
    with TestClient(build(tmp_path)) as client:
        client.post("/api/v1/auth/register", json={"name": "A", "email": "a@x.test", "password": PASSWORD, "city": "Pune", "pincode": "411001"})
        bad = {"email": "a@x.test", "password": "wrong password!"}
        assert [client.post("/api/v1/auth/login", json=bad).status_code for _ in range(3)] == [401, 401, 401]
        blocked = client.post("/api/v1/auth/login", json={"email": "a@x.test", "password": PASSWORD})
        assert blocked.status_code == 429 and blocked.headers["retry-after"]
        # someone else's address is unaffected
        assert client.post("/api/v1/auth/login", json={"email": "b@x.test", "password": "whatever-1234"}).status_code == 401


def test_a_good_sign_in_resets_the_count(tmp_path, monkeypatch):
    monkeypatch.setenv("CIVICLOOP_LOGIN_ATTEMPTS", "3")
    with TestClient(build(tmp_path)) as client:
        client.post("/api/v1/auth/register", json={"name": "A", "email": "a@x.test", "password": PASSWORD, "city": "Pune", "pincode": "411001"})
        for _ in range(2):
            client.post("/api/v1/auth/login", json={"email": "a@x.test", "password": "wrong password!"})
        assert client.post("/api/v1/auth/login", json={"email": "a@x.test", "password": PASSWORD}).status_code == 200
        for _ in range(2):
            assert client.post("/api/v1/auth/login", json={"email": "a@x.test", "password": "wrong password!"}).status_code == 401


def test_registration_is_rate_limited(tmp_path, monkeypatch):
    monkeypatch.setenv("CIVICLOOP_REGISTER_LIMIT", "2")
    with TestClient(build(tmp_path)) as client:
        codes = [client.post("/api/v1/auth/register", json={"name": "A", "email": f"a{i}@x.test", "password": PASSWORD, "city": "Pune", "pincode": "411001"}).status_code for i in range(3)]
        assert codes == [201, 201, 429]


def test_oversized_credentials_are_refused(world):
    client, w, make = world
    assert client.post("/api/v1/auth/login", json={"email": "a@x.test", "password": "p" * 300}).status_code == 422
    assert client.post("/api/v1/auth/register", json={"name": "A", "email": "z@x.test", "password": "p" * 300, "city": "Pune", "pincode": "411001"}).status_code == 422


def test_a_damaged_stored_hash_is_a_failed_sign_in_not_a_crash():
    assert verify_password("anything", "scrypt$1$only-one-part") is False
    assert verify_password("anything", "scrypt$1$%%%$%%%") is False
    good = hash_password(PASSWORD)
    assert verify_password(PASSWORD, good) is True and verify_password("nope", good) is False


# ------------------------------------------------------------------ F-22 revoking sign-ins


def test_sign_out_everywhere_ends_every_earlier_sign_in(world):
    client, w, make = world
    other_session = client.post("/api/v1/auth/login", json={"email": "res@x.test", "password": PASSWORD}).json()["access_token"]
    assert client.get("/api/v1/incidents", headers=w["resident"]).status_code == 200
    assert client.post("/api/v1/auth/logout-all", headers=w["resident"]).status_code == 204
    assert client.get("/api/v1/incidents", headers=w["resident"]).status_code == 401
    assert client.get("/api/v1/incidents", headers={"Authorization": f"Bearer {other_session}"}).status_code == 401
    fresh = client.post("/api/v1/auth/login", json={"email": "res@x.test", "password": PASSWORD}).json()["access_token"]
    assert client.get("/api/v1/incidents", headers={"Authorization": f"Bearer {fresh}"}).status_code == 200


# ------------------------------------------------------------------ F-05 reserved platform-admin addresses


def test_a_platform_admin_address_cannot_be_claimed_by_a_sign_up(tmp_path, monkeypatch):
    monkeypatch.setenv("CIVICLOOP_PLATFORM_ADMINS", "root@x.test")
    with TestClient(build(tmp_path)) as client:
        claim = client.post("/api/v1/auth/register", json={"name": "Eve", "email": "root@x.test", "password": PASSWORD, "role": "admin", "city": "Nowhere", "pincode": "411001"})
        assert claim.status_code == 403 and "reserved" in claim.json()["detail"]
        # a normal address still creates a city and its first admin
        assert client.post("/api/v1/auth/register", json={"name": "Ok", "email": "ok@x.test", "password": PASSWORD, "role": "admin", "city": "Nowhere", "pincode": "411001"}).status_code == 201


# ------------------------------------------------------------------ F-04, F-06 production safety


def test_production_refuses_memory_storage_and_queue(tmp_path, monkeypatch):
    monkeypatch.setenv("CIVICLOOP_ENV", "production")
    url = f"sqlite:///{tmp_path / 'p.db'}"
    with pytest.raises(ValueError, match="in-memory storage"):
        create_app(database_url=url, auth_secret=SECRET, storage=InMemoryObjectStorage(), queue=InMemoryJobQueue())
    from civicloop.storage import LocalFilesystemObjectStorage

    with pytest.raises(ValueError, match="in-memory queue"):
        create_app(database_url=url, auth_secret=SECRET, storage=LocalFilesystemObjectStorage(tmp_path / "up"), queue=InMemoryJobQueue())


def test_the_schema_check_names_the_fix(tmp_path):
    from civicloop.db import assert_schema_current

    engine = create_engine(f"sqlite:///{tmp_path / 's.db'}")
    init_db(engine)  # tables exist but were never stamped by alembic
    with pytest.raises(RuntimeError, match="alembic upgrade head"):
        assert_schema_current(engine)


# ------------------------------------------------------------------ F-03 SQLite settings


def test_sqlite_connections_enforce_foreign_keys_and_wait_for_locks(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'f.db'}")
    init_db(engine)
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert connection.execute(text("PRAGMA journal_mode")).scalar().lower() == "wal"
        assert connection.execute(text("PRAGMA busy_timeout")).scalar() >= 5000
    with Session(engine) as session:
        session.add(Incident(reporter_id="no-such-user", reporter_type=ReporterType.RESIDENT, description="x", latitude=1, longitude=1, occurred_at=datetime.now(timezone.utc)))
        with pytest.raises(IntegrityError):
            session.commit()


# ------------------------------------------------------------------ F-02, F-07, F-18 jobs


def worker_for(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'j.db'}")
    init_db(engine)
    factory = create_session_factory(engine)
    queue = InMemoryJobQueue()
    calls: list[str] = []

    def handlers(session):
        return {"noop": lambda payload: calls.append("ran") or {"ok": True}}

    return factory, queue, JobWorker(factory, queue, handlers), calls


def add_job(factory, key, **fields):
    with factory() as session:
        job = JobRepository(session).add(Job(job_type="noop", payload={}, idempotency_key=key, **fields))
        session.commit()
        return job.id


def test_recovery_requeues_lost_jobs_and_gives_up_on_exhausted_ones(tmp_path):
    factory, queue, worker, calls = worker_for(tmp_path)
    hour_ago = utc_now() - timedelta(hours=1)
    stuck = add_job(factory, "stuck", status=JobStatus.RUNNING, started_at=hour_ago, attempt_count=1)
    worn_out = add_job(factory, "worn", status=JobStatus.RUNNING, started_at=hour_ago, attempt_count=3, max_attempts=3)
    never_queued = add_job(factory, "orphan")  # saved, but the process died before it was queued
    fresh = add_job(factory, "fresh", status=JobStatus.RUNNING, started_at=utc_now(), attempt_count=1)

    assert recover_jobs(worker) == 2
    with factory() as session:
        repo = JobRepository(session)
        assert repo.get(stuck).status == JobStatus.QUEUED
        assert repo.get(worn_out).status == JobStatus.DEAD_LETTER and repo.get(worn_out).last_error_code == "worker_lost"
        assert repo.get(fresh).status == JobStatus.RUNNING  # a live worker may still be on it
    while worker.run_once():
        pass
    with factory() as session:
        repo = JobRepository(session)
        assert repo.get(stuck).status == JobStatus.SUCCEEDED and repo.get(never_queued).status == JobStatus.SUCCEEDED
    assert calls == ["ran", "ran"]


def test_a_second_delivery_of_a_running_job_does_not_run_it_twice(tmp_path):
    factory, queue, worker, calls = worker_for(tmp_path)
    running = add_job(factory, "busy", status=JobStatus.RUNNING, started_at=utc_now(), attempt_count=1)
    queue.enqueue(running)
    assert worker.run_once() is True
    assert calls == []


def test_a_retry_waits_on_a_timer_and_does_not_block_the_worker():
    queue = InMemoryJobQueue()
    started = time.monotonic()
    queue.retry(JobDelivery(job_id="j1", priority="normal", delivery_id="d"), 1)
    assert time.monotonic() - started < 0.3  # it used to sleep here, freezing every other job
    assert queue.dequeue() is None
    time.sleep(1.3)
    assert queue.dequeue().job_id == "j1"


# ------------------------------------------------------------------ F-09 tenant scope cannot be dropped by accident


def test_a_request_session_cannot_lift_its_city_scope_by_mistake(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    init_db(engine)
    with create_session_factory(engine)() as session:
        session.info["request_scoped"] = True
        bind_tenant(session, "city-1")
        with pytest.raises(RuntimeError, match="lift_scope"):
            bind_tenant(session, None)
        lift_scope(session)  # the deliberate way, used by the platform routes
        assert "tenant_id" not in session.info
    with create_session_factory(engine)() as worker_session:
        bind_tenant(worker_session, None)  # workers and tools may still run unscoped


# ------------------------------------------------------------------ F-10 municipal imports cannot skip the work flow


def make_order(client, w, label="Pile"):
    inc = report(client, w["resident"], description=label).json()
    client.post(f"/api/v1/incidents/{inc['id']}/media", headers=w["resident"], files={"file": ("a.jpg", JPEG, "image/jpeg")})
    assert client.post(f"/api/v1/incidents/{inc['id']}/analysis", headers=w["sup"]).status_code == 200
    order = client.post(f"/api/v1/incidents/{inc['id']}/work-orders", headers=w["sup"], json={"priority": 50, "estimated_volume": 1})
    assert order.status_code == 201, order.text
    return inc, order.json()


def test_a_municipal_import_cannot_jump_a_draft_to_completed(world):
    client, w, make = world
    inc, order = make_order(client, w)
    jump = client.post("/api/v1/municipal/import", headers=w["sup"], json={"updates": [{"work_order_id": order["id"], "status": "completed"}]})
    assert jump.status_code == 200 and jump.json() == {"imported": 0, "received": 1}
    assert client.get(f"/api/v1/work-orders/{order['id']}", headers=w["sup"]).json()["status"] == "draft"
    # a real move is still accepted: an assigned job reported as started by the outside system
    client.post(f"/api/v1/work-orders/{order['id']}/approve", headers=w["sup"])
    client.post(f"/api/v1/work-orders/{order['id']}/assign", headers=w["sup"], json={"worker_id": w["worker_id"]})
    ok = client.post("/api/v1/municipal/import", headers=w["sup"], json={"updates": [{"work_order_id": order["id"], "status": "in_progress"}]})
    assert ok.json()["imported"] == 1


# ------------------------------------------------------------------ F-14 one live order per incident


def test_the_database_allows_only_one_live_work_order_per_incident(world):
    client, w, make = world
    inc, order = make_order(client, w)
    again = client.post(f"/api/v1/incidents/{inc['id']}/work-orders", headers=w["sup"], json={"priority": 10})
    assert again.status_code == 400 and "already has an active work order" in again.json()["detail"]
    factory = client.app.state.session_factory
    with factory() as session:  # even bypassing the service check, the index refuses a second live order
        session.add(WorkOrder(incident_id=inc["id"], priority=1, status=WorkOrderStatus.DRAFT, tenant_id=session.get(Incident, inc["id"]).tenant_id))
        with pytest.raises(IntegrityError):
            session.commit()
    # cancelling the first frees the incident for a new one
    with factory() as session:
        session.get(WorkOrder, order["id"]).status = WorkOrderStatus.CANCELLED
        session.commit()
    with factory() as session:
        session.add(WorkOrder(incident_id=inc["id"], priority=1, status=WorkOrderStatus.DRAFT, tenant_id=session.get(Incident, inc["id"]).tenant_id))
        session.commit()


# ------------------------------------------------------------------ F-11, F-20 uploads


def test_uploads_are_judged_by_their_bytes(world):
    client, w, make = world
    inc = report(client, w["resident"]).json()
    url = f"/api/v1/incidents/{inc['id']}/media"
    svg = client.post(url, headers=w["resident"], files={"file": ("a.svg", b"<svg onload=alert(1)></svg>", "image/jpeg")})
    assert svg.status_code == 400
    text_file = client.post(url, headers=w["resident"], files={"file": ("a.jpg", b"just text", "image/jpeg")})
    assert text_file.status_code == 400
    # the label is wrong but the bytes are a JPEG: stored as what it really is
    stored = client.post(url, headers=w["resident"], files={"file": ("a.png", JPEG, "image/png")})
    assert stored.status_code == 201 and stored.json()["content_type"] == "image/jpeg"
    shown = client.get(f"/api/v1/media/{stored.json()['id']}/content", headers=w["resident"])
    assert shown.headers["x-content-type-options"] == "nosniff" and "sandbox" in shown.headers["content-security-policy"]


def test_a_report_holds_at_most_eight_photos(world):
    client, w, make = world
    inc = report(client, w["resident"]).json()
    url = f"/api/v1/incidents/{inc['id']}/media"
    codes = [client.post(url, headers=w["resident"], files={"file": ("a.jpg", JPEG + bytes([i]), "image/jpeg")}).status_code for i in range(9)]
    assert codes == [201] * 8 + [409]


# ------------------------------------------------------------------ F-12, F-17, F-26 creating a report


def test_sending_a_report_twice_with_one_key_gives_one_report(world):
    client, w, make = world
    first = report(client, w["resident"], key="draft-1")
    second = report(client, w["resident"], key="draft-1")
    assert first.status_code == 201 and second.status_code == 200 and first.json()["id"] == second.json()["id"]
    other = report(client, w["resident"], key="draft-2")
    assert other.status_code == 201 and other.json()["id"] != first.json()["id"]
    assert len(client.get("/api/v1/incidents", headers=w["resident"]).json()) == 2
    # the same key from someone else is their own report
    mine = report(client, w["sup"], key="draft-1", reporter_type="field_worker")
    assert mine.status_code == 201 and mine.json()["id"] != first.json()["id"]


def test_report_fields_have_sensible_limits(world):
    client, w, make = world
    assert report(client, w["resident"], description="x" * 4001).status_code == 422
    future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    assert report(client, w["resident"], occurred_at=future).status_code == 422
    # a time with no zone is read as UTC instead of breaking later comparisons
    naive = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    assert report(client, w["resident"], occurred_at=naive).status_code == 201


def test_list_inputs_are_bounded(world):
    client, w, make = world
    too_many = [f"id{i}" for i in range(61)]
    assert client.post("/api/v1/routes", headers=w["sup"], json={"work_order_ids": too_many, "vehicle_capacity": 10}).status_code == 422
    assert client.post("/api/v1/routes/preview", headers=w["sup"], json={"work_order_ids": too_many, "vehicle_capacity": 10}).status_code == 422
    assert client.post("/api/v1/municipal/export", headers=w["sup"], json={"work_order_ids": [f"i{i}" for i in range(501)]}).status_code == 422


# ------------------------------------------------------------------ F-21 analysis


def test_a_second_click_on_analyse_reuses_the_first_result(world):
    client, w, make = world
    inc = report(client, w["resident"]).json()
    client.post(f"/api/v1/incidents/{inc['id']}/media", headers=w["resident"], files={"file": ("a.jpg", JPEG, "image/jpeg")})
    a = client.post(f"/api/v1/incidents/{inc['id']}/analysis", headers=w["sup"]).json()
    b = client.post(f"/api/v1/incidents/{inc['id']}/analysis", headers=w["sup"]).json()
    assert a["id"] == b["id"] and b["status"] == "ready_for_review"


# ------------------------------------------------------------------ F-31, F-36 small leaks


def test_city_search_treats_percent_and_underscore_as_letters(world):
    client, w, make = world
    assert client.get("/api/v1/tenants", params={"q": "__"}).json() == []
    assert client.get("/api/v1/tenants", params={"q": "%%"}).json() == []


def test_residents_cannot_read_job_status(world):
    client, w, make = world
    assert client.get("/api/v1/jobs/anything", headers=w["resident"]).status_code == 403


# ------------------------------------------------------------------ F-27 a tracker flood is refused


def test_a_device_cannot_flood_the_tracker_endpoint(world, monkeypatch):
    import civicloop.routes_fleet as fleet

    monkeypatch.setattr(fleet, "DEVICE_LIMIT", 3)
    fleet._device_hits.clear()
    client, w, make = world
    vehicle = client.post("/api/v1/vehicles", headers=w["sup"], json={"label": "Truck 1"}).json()
    device = {"X-Device-Key": vehicle["device_key"]}
    now = datetime.now(timezone.utc)
    codes = [client.post("/api/v1/telemetry/gps", headers=device, json={"lat": 30.7, "lon": 76.77, "recorded_at": (now + timedelta(seconds=i)).isoformat()}).status_code for i in range(5)]
    assert codes == [200, 200, 200, 429, 429]
    fleet._device_hits.clear()


# ------------------------------------------------------------------ F-18 Redis retries wait their turn


class FakeRedis:
    """Just the few Redis commands the queue uses, kept in memory."""

    def __init__(self):
        self.lists, self.sets = {}, {}

    def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)

    def lpop(self, key):
        items = self.lists.get(key, [])
        return items.pop(0) if items else None

    def zadd(self, key, mapping):
        self.sets.setdefault(key, {}).update(mapping)

    def zrangebyscore(self, key, low, high):
        return [m for m, score in sorted(self.sets.get(key, {}).items(), key=lambda kv: kv[1]) if low <= score <= high]

    def zrem(self, key, member):
        return 1 if self.sets.get(key, {}).pop(member, None) is not None else 0


def test_a_redis_retry_is_held_until_it_is_due_instead_of_spinning():
    from civicloop.jobs import RedisJobQueue

    queue = object.__new__(RedisJobQueue)
    queue.client, queue.prefix = FakeRedis(), "t"
    delivery = JobDelivery(job_id="j1", priority="high", delivery_id="d")
    queue.retry(delivery, 60)
    assert queue.dequeue() is None  # not due yet: the worker is not handed it again and again
    queue.client.sets["t:delayed"] = {k: 0 for k in queue.client.sets["t:delayed"]}  # time passes
    got = queue.dequeue()
    assert got.job_id == "j1" and got.priority == "high"
    assert queue.dequeue() is None


# ------------------------------------------------------------------ F-06 the migrations really build the schema the code expects


def test_alembic_builds_a_database_the_code_accepts(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config

    from civicloop.db import assert_schema_current

    url = f"sqlite:///{tmp_path / 'm.db'}"
    monkeypatch.setenv("CIVICLOOP_DATABASE_URL", url)
    command.upgrade(Config("alembic.ini"), "head")
    engine = create_engine(url)
    assert_schema_current(engine)
    columns = {c["name"] for c in inspect(engine).get_columns("users")}
    assert "token_version" in columns
    assert "client_key" in {c["name"] for c in inspect(engine).get_columns("incidents")}


# ------------------------------------------------------------------ deploying on a host such as Render


def test_one_process_may_use_the_in_memory_queue_when_it_says_so(tmp_path, monkeypatch):
    from civicloop.storage import LocalFilesystemObjectStorage

    monkeypatch.setenv("CIVICLOOP_ENV", "production")
    monkeypatch.setenv("CIVICLOOP_ALLOW_SINGLE_PROCESS", "1")
    app = create_app(database_url=f"sqlite:///{tmp_path / 'p.db'}", auth_secret=SECRET, storage=LocalFilesystemObjectStorage(tmp_path / "up"), queue=InMemoryJobQueue())
    assert app.title == "CivicLoopAI API"


def test_host_database_addresses_are_made_to_use_psycopg():
    from civicloop.db import normalise_database_url

    assert normalise_database_url("postgres://u:p@h:5432/d") == "postgresql+psycopg://u:p@h:5432/d"
    assert normalise_database_url("postgresql://u:p@h/d") == "postgresql+psycopg://u:p@h/d"
    assert normalise_database_url("postgresql+psycopg://u:p@h/d") == "postgresql+psycopg://u:p@h/d"
    assert normalise_database_url("sqlite:///x.db") == "sqlite:///x.db"


def test_supabase_addresses_get_encryption_and_the_pooler_is_recognised():
    from civicloop.db import normalise_database_url, uses_transaction_pooler

    direct = normalise_database_url("postgresql://postgres:pw@db.abcdefgh.supabase.co:5432/postgres")
    assert direct.startswith("postgresql+psycopg://") and "sslmode=require" in direct
    pooled = normalise_database_url("postgresql://postgres.abcdefgh:pw@aws-0-ap-south-1.pooler.supabase.com:6543/postgres")
    assert "sslmode=require" in pooled and uses_transaction_pooler(pooled) is True
    session_mode = normalise_database_url("postgres://postgres.abcdefgh:pw@aws-0-ap-south-1.pooler.supabase.com:5432/postgres")
    assert uses_transaction_pooler(session_mode) is False
    already = normalise_database_url("postgresql://u:p@db.abcdefgh.supabase.co:5432/postgres?sslmode=verify-full")
    assert already.count("sslmode") == 1 and "verify-full" in already
    # other hosts are left as they are
    assert "sslmode" not in normalise_database_url("postgresql://u:p@db.internal:5432/d")


def test_production_refuses_a_placeholder_secret_copied_from_an_example_file(tmp_path, monkeypatch):
    from civicloop.storage import LocalFilesystemObjectStorage

    monkeypatch.setenv("CIVICLOOP_ENV", "production")
    monkeypatch.setenv("CIVICLOOP_ALLOW_SINGLE_PROCESS", "1")
    for placeholder in ("PASTE_A_LONG_RANDOM_SECRET_PASTE_A_LONG", "replace-with-a-random-32-character-secret"):
        with pytest.raises(ValueError, match="placeholder"):
            create_app(database_url=f"sqlite:///{tmp_path / 'p.db'}", auth_secret=placeholder, storage=LocalFilesystemObjectStorage(tmp_path / "up"), queue=InMemoryJobQueue())


# ------------------------------------------------------------------ cross-origin browser access is opt-in


def test_cors_is_off_unless_origins_are_listed(tmp_path, monkeypatch):
    ask = {"Origin": "https://app.example.org", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type,authorization"}
    monkeypatch.delenv("CIVICLOOP_CORS_ORIGINS", raising=False)
    with TestClient(build(tmp_path)) as client:
        off = client.options("/api/v1/auth/login", headers=ask)
        assert "access-control-allow-origin" not in off.headers

    monkeypatch.setenv("CIVICLOOP_CORS_ORIGINS", "https://app.example.org/, https://other.example.org")
    with TestClient(build(tmp_path)) as client:
        listed = client.options("/api/v1/auth/login", headers=ask)
        assert listed.status_code == 200 and listed.headers["access-control-allow-origin"] == "https://app.example.org"
        assert "authorization" in listed.headers["access-control-allow-headers"].lower()
        stranger = client.options("/api/v1/auth/login", headers={**ask, "Origin": "https://evil.example.com"})
        assert "access-control-allow-origin" not in stranger.headers
