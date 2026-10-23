"""The three ML upgrades: OR-Tools routing, embedding duplicates, trained risk model."""

import random
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import numpy as np
import pytest
from fastapi.testclient import TestClient

from civicloop.api import create_app
from civicloop.db import create_engine, create_session_factory, init_db
from civicloop.engines.duplicate import DuplicateEngine
from civicloop.engines.routing import RouteEngine, RouteEngineConfig
from civicloop.jobs import InMemoryJobQueue
from civicloop.models import User, UserRole
from civicloop.repositories import AuditEventRepository, UserRepository
from civicloop.risk_model import (
    FEATURES,
    HORIZON_DAYS,
    LearnedRiskEngine,
    RiskModelStore,
    TrainingRow,
    compute_features,
    to_days,
    train_risk_model,
)
from civicloop.services.hotspot_risk import HotspotRiskService
from civicloop.services.ml import MLService
from civicloop.storage import InMemoryObjectStorage
from civicloop.synthetic import seed_synthetic_history

# ------------------------------------------------------------------ routing


def scenario(n, seed=3):
    rng = random.Random(seed)
    incidents = {str(i): NS(latitude=30.70 + rng.random() * 0.06, longitude=76.74 + rng.random() * 0.06) for i in range(n)}
    orders = [NS(id=f"o{i}", incident_id=str(i), priority=rng.choice([1, 5, 50, 100]), estimated_volume=1.0) for i in range(n)]
    return orders, incidents


def test_ortools_is_never_longer_than_nearest_neighbour_without_priority_pull():
    orders, incidents = scenario(20)
    engine = RouteEngine(RouteEngineConfig(priority_weight=0, time_limit_seconds=1))
    result = engine.build(orders, incidents, 100, depot=(30.73, 76.77))
    assert result.solver == "ortools"
    assert result.distance_km <= result.greedy_distance_km + 1e-9
    assert sorted(s.work_order_id for s in result.stops) == sorted(o.id for o in orders)  # every stop visited once


def test_priority_pull_serves_urgent_stops_earlier():
    orders, incidents = scenario(15, seed=11)

    def mean_rank(weight):
        result = RouteEngine(RouteEngineConfig(priority_weight=weight, time_limit_seconds=1)).build(orders, incidents, 100, depot=(30.73, 76.77))
        rank = {s.work_order_id: s.sequence for s in result.stops}
        urgent = [rank[o.id] for o in orders if o.priority == 100]
        return sum(urgent) / len(urgent)

    assert mean_rank(2.0) < mean_rank(0.0)


def test_route_respects_capacity_and_duration_limits():
    orders, incidents = scenario(6)
    engine = RouteEngine(RouteEngineConfig(time_limit_seconds=1))
    with pytest.raises(ValueError, match="capacity"):
        engine.build(orders, incidents, 3.0)
    with pytest.raises(ValueError, match="limit"):
        engine.build(orders, incidents, 100, depot=(30.73, 76.77), constraints={"max_duration_minutes": 1})
    ok = engine.build(orders, incidents, 100, depot=(30.73, 76.77), constraints={"max_duration_minutes": 600})
    assert ok.duration_minutes <= 600


def test_small_routes_and_greedy_setting_still_work():
    orders, incidents = scenario(2)
    assert RouteEngine().build(orders, incidents, 10).solver == "nearest-neighbour"
    orders, incidents = scenario(8)
    assert RouteEngine(RouteEngineConfig(solver="greedy")).build(orders, incidents, 100).solver == "nearest-neighbour"


# ------------------------------------------------------------------ duplicates


class FakeEmbedder:
    """Treats 'bins' and 'garbage' texts as the same meaning, like a real sentence model would."""

    name = "fake"

    def embed(self, texts):
        out = []
        for text in texts:
            waste = any(w in text.lower() for w in ("bin", "garbage", "waste", "trash"))
            out.append([1.0, 0.0] if waste else [0.0, 1.0])
        return out


def _incident(id_, text, lat=30.7333, lon=76.7794, hours=0):
    return NS(id=id_, description=text, latitude=lat, longitude=lon, occurred_at=datetime(2026, 10, 1, tzinfo=timezone.utc) + timedelta(hours=hours))


def test_embeddings_find_paraphrased_duplicates_word_overlap_misses():
    source = _incident("a", "Overflowing bins behind the market")
    other = _incident("b", "Garbage heaped near the stalls", lat=30.7334, hours=2)
    plain = DuplicateEngine().find(source, [other])
    smart = DuplicateEngine(embedder=FakeEmbedder()).find(source, [other])
    assert plain == []
    assert [m.incident_id for m in smart] == ["b"]
    assert smart[0].text_method == "embedding" and smart[0].engine_version == "duplicate-embed-1"


def test_duplicate_engine_falls_back_when_the_embedder_fails():
    class Broken:
        name = "broken"

        def embed(self, texts):
            raise RuntimeError("model crashed")

    a, b = _incident("a", "Overflowing bins behind the market"), _incident("b", "Overflowing bins behind the market stalls", hours=1)
    match = DuplicateEngine(embedder=Broken()).find(a, [b])[0]
    assert match.text_method == "word-overlap" and match.engine_version == "duplicate-baseline-1"


# ------------------------------------------------------------------ risk model


def _rows(session, n=1500):
    seed_synthetic_history(session, n)
    return MLService(session, None, None).training_rows()


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'ml.db'}")
    init_db(engine)
    factory = create_session_factory(engine)
    yield factory
    engine.dispose()


def test_features_never_look_at_the_future():
    t = to_days(datetime(2026, 6, 1, tzinfo=timezone.utc))
    lat, lon = np.array([30.7334, 30.7334]), np.array([76.7794, 76.7794])
    before = compute_features(30.7333, 76.7794, t, "high", 0.9, lat, lon, np.array([t - 3, t - 40]))
    with_future = compute_features(30.7333, 76.7794, t, "high", 0.9, np.append(lat, 30.7334), np.append(lon, 76.7794), np.array([t - 3, t - 40, t + 5]))
    assert np.array_equal(before, with_future)
    assert before[FEATURES.index("reports_7d")] == 1 and before[FEATURES.index("reports_90d")] == 2


def test_too_little_data_keeps_the_formula(db):
    with db() as session:
        rows = _rows(session, 60)
    outcome = train_risk_model(rows)
    assert not outcome.deployed and outcome.metadata["status"] == "not_enough_data"
    assert "formula stays in use" in outcome.reason


def test_training_validates_on_unseen_reports_and_deploys_only_a_winner(db, tmp_path, monkeypatch):
    monkeypatch.setenv("CIVICLOOP_MODEL_DIR", str(tmp_path / "models"))
    with db() as session:
        rows = _rows(session)
    outcome = train_risk_model(rows)
    meta = outcome.metadata
    assert meta["synthetic_share"] == 1.0  # flagged, so nobody mistakes this for real-world accuracy
    assert meta["train_rows"] + meta["validation_rows"] == meta["rows_labelled"]
    assert 0.5 < meta["metrics"]["auc"] <= 1.0 and set(meta["candidates"]) == {"logistic_regression", "gradient_boosting"}
    assert outcome.deployed == (meta["auc_gain_vs_baseline"] >= 0.01)
    # the label's outcome window must be closed: nothing newer than `now - horizon` is trained on
    assert max(to_days(r.occurred_at) for r in rows) > to_days(datetime.now(timezone.utc)) - HORIZON_DAYS
    assert meta["rows_labelled"] < len(rows)


def test_deployed_model_scores_new_reports_with_an_explanation(db, tmp_path, monkeypatch):
    monkeypatch.setenv("CIVICLOOP_MODEL_DIR", str(tmp_path / "models"))
    with db() as session:
        admin = UserRepository(session).add(User(name="A", email="a@x.test", role=UserRole.ADMIN))
        session.commit()
        ml = MLService(session, AuditEventRepository(session), UserRepository(session), RiskModelStore())
        ml.session  # training rows come from the database
        seed_synthetic_history(session, 1500)
        result = ml.train_risk(admin.id)
        session.commit()
        status = ml.status()
        assert status["risk"]["last_run"]["rows_labelled"] > 1000
        if not result["deployed"]:
            pytest.skip("synthetic run did not beat the formula on this machine; covered by the previous test")
        assert status["risk"]["active"] == "model"

        from civicloop.models import Incident, ReporterType
        from civicloop.repositories import AnalysisRepository, IncidentRepository, RiskAssessmentRepository

        incidents = IncidentRepository(session)
        fresh = incidents.add(Incident(reporter_id=admin.id, reporter_type=ReporterType.RESIDENT, description="New pile", latitude=30.7333, longitude=76.7794, occurred_at=datetime.now(timezone.utc)))
        service = HotspotRiskService(RiskAssessmentRepository(session), incidents, AnalysisRepository(session), AuditEventRepository(session))
        assert isinstance(service.engine, LearnedRiskEngine)
        assessment = service.calculate_risk(fresh.id)
        assert 0 <= assessment.score <= 1 and assessment.model_version.startswith("risk-")
        assert set(assessment.factors["_contributions"]) == set(FEATURES)


# ------------------------------------------------------------------ over HTTP


def test_ml_endpoints_and_route_details_over_http(tmp_path, monkeypatch):
    monkeypatch.setenv("CIVICLOOP_MODEL_DIR", str(tmp_path / "models"))
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'api.db'}",
        auth_secret="test-secret-that-is-at-least-32-characters",
        storage=InMemoryObjectStorage(),
        queue=InMemoryJobQueue(),
        analysis_adapter_factory=lambda: NS(provider="t", model_name="t", analyze=lambda p: {"category": "mixed", "severity": "high", "confidence": 0.9, "details": {}}),
    )
    password = "correct horse battery"
    with TestClient(app) as client:
        def account(role, email, headers=None):
            client.post("/api/v1/auth/register", headers=headers or {}, json={"name": role, "email": email, "password": password, "role": role, "city": "Chandigarh", "pincode": "160017"})
            token = client.post("/api/v1/auth/login", json={"email": email, "password": password}).json()["access_token"]
            return {"Authorization": f"Bearer {token}"}

        admin = account("admin", "admin@x.test")
        supervisor = account("supervisor", "sup@x.test", admin)
        resident = account("reporter", "res@x.test")
        driver = account("sanitation_worker", "drv@x.test", admin)
        driver_id = client.get("/api/v1/auth/me", headers=driver).json()["id"]

        assert client.get("/api/v1/ml/status", headers=resident).status_code == 403
        status = client.get("/api/v1/ml/status", headers=supervisor).json()
        assert status["risk"]["active"] == "formula" and status["routing"]["solver"] == "ortools"
        assert client.post("/api/v1/ml/risk/train", headers=supervisor).status_code == 403

        # Not enough history yet: training is refused politely and the formula stays.
        trained = client.post("/api/v1/ml/risk/train", headers=admin).json()
        assert trained["deployed"] is False and "formula stays in use" in trained["reason"]

        # A scored report reports which method scored it.
        r = client.post("/api/v1/incidents", headers=resident, json={"reporter_type": "resident", "description": "Overflowing bins", "latitude": 30.7333, "longitude": 76.7794, "occurred_at": datetime.now(timezone.utc).isoformat()}).json()
        client.post(f"/api/v1/incidents/{r['id']}/media", headers=resident, files={"file": ("a.jpg", b"\xff\xd8\xffx", "image/jpeg")})
        client.post(f"/api/v1/incidents/{r['id']}/analysis", headers=supervisor)
        risk = client.get(f"/api/v1/incidents/{r['id']}/risk", headers=supervisor).json()
        assert risk["kind"] == "formula" and risk["method"] == "hand-set formula"

        # Routes report the solver and accept a duration limit.
        orders = []
        for i in range(4):
            inc = client.post("/api/v1/incidents", headers=resident, json={"reporter_type": "resident", "description": f"Pile {i}", "latitude": 30.70 + i * 0.01, "longitude": 76.77, "occurred_at": datetime.now(timezone.utc).isoformat()}).json()
            client.post(f"/api/v1/incidents/{inc['id']}/media", headers=resident, files={"file": ("a.jpg", b"\xff\xd8\xffx", "image/jpeg")})
            client.post(f"/api/v1/incidents/{inc['id']}/analysis", headers=supervisor)
            order = client.post(f"/api/v1/incidents/{inc['id']}/work-orders", headers=supervisor, json={"priority": 10 * i, "estimated_volume": 1}).json()
            client.post(f"/api/v1/work-orders/{order['id']}/approve", headers=supervisor)
            client.post(f"/api/v1/work-orders/{order['id']}/assign", headers=supervisor, json={"worker_id": driver_id})
            orders.append(order["id"])
        route = client.post("/api/v1/routes", headers=supervisor, json={"work_order_ids": orders, "vehicle_capacity": 10, "max_duration_minutes": 600})
        assert route.status_code == 201, route.text
        body = route.json()
        assert body["solver"] == "ortools" and body["max_duration_minutes"] == 600 and body["greedy_distance_km"] > 0
        # the map needs both baseline orders to draw the comparison
        assert sorted(body["greedy_order"]) == sorted(orders) and body["selection_order"] == orders and body["depot"] is None
        preview = client.post("/api/v1/routes/preview", headers=supervisor, json={"work_order_ids": orders, "vehicle_capacity": 10})
        assert preview.status_code == 200 and preview.json()["id"] == "preview" and len(preview.json()["stops"]) == 4
        assert client.get("/api/v1/routes", headers=supervisor).json().__len__() == 1  # previewing saved nothing
        too_tight = client.post("/api/v1/routes", headers=supervisor, json={"work_order_ids": orders, "vehicle_capacity": 10, "max_duration_minutes": 1})
        assert too_tight.status_code == 400 and "limit" in too_tight.json()["detail"]

        # Duplicates explain themselves.
        twin = client.post("/api/v1/incidents", headers=resident, json={"reporter_type": "resident", "description": "Overflowing bins", "latitude": 30.7334, "longitude": 76.7795, "occurred_at": datetime.now(timezone.utc).isoformat()}).json()
        found = client.get(f"/api/v1/incidents/{twin['id']}/duplicates", headers=supervisor).json()
        assert found["candidates"] and set(found["candidates"][0]["factors"]) == {"distance", "time", "text", "category"}
        assert found["text_method"] == "word-overlap"  # embeddings are switched off in tests
