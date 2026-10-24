import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from civicloop.engines.common import haversine_km, jaccard_text, normalize_text
from civicloop.engines.duplicate import DuplicateEngine
from civicloop.engines.risk import RiskEngine
from civicloop.engines.routing import RouteEngine


def load_cases():
    path = Path(__file__).parent / "fixtures" / "deterministic_engine_cases.json"
    return json.loads(path.read_text(encoding="utf-8"))


def incident(identifier, description, latitude, longitude, occurred_at, status="ready_for_review"):
    return SimpleNamespace(id=identifier, description=description, latitude=latitude, longitude=longitude, occurred_at=occurred_at, status=status)


def test_common_geographic_and_text_utilities():
    assert haversine_km((30.7333, 76.7794), (30.7333, 76.7794)) == 0
    assert normalize_text(" Black-Bags!  ") == "black bags"
    assert jaccard_text("Black bags beside market", "black bags beside market") == 1


def test_duplicate_engine_matches_fixture_candidate():
    case = load_cases()["duplicate"]
    source = incident("incident-source", case["source"]["description"], case["source"]["latitude"], case["source"]["longitude"], datetime.fromisoformat(case["source"]["occurred_at"]))
    candidate = incident("incident-candidate", case["candidate"]["description"], case["candidate"]["latitude"], case["candidate"]["longitude"], datetime.fromisoformat(case["candidate"]["occurred_at"]))
    source_analysis = SimpleNamespace(category="mixed_waste")
    candidate_analysis = SimpleNamespace(category="mixed_waste")

    result = DuplicateEngine().compare(source, candidate, source_analysis, candidate_analysis)

    assert result is not None
    assert result.similarity_score >= case["expected_minimum_score"]
    assert result.engine_version == "duplicate-baseline-1"


def test_duplicate_engine_excludes_out_of_range_candidates():
    source = incident("source", "waste", 30.7333, 76.7794, datetime.now(timezone.utc))
    far = incident("far", "waste", 31.5, 77.5, datetime.now(timezone.utc))

    assert DuplicateEngine().find(source, [far]) == []


def test_risk_engine_is_reproducible_and_bounded():
    case = load_cases()["risk"]
    cutoff = datetime.fromisoformat(case["cutoff_at"])
    target = incident("target", "waste", case["target_latitude"], case["target_longitude"], cutoff)
    history = [
        incident("old", "waste", 30.7334, 76.7795, datetime(2026, 9, 1, tzinfo=timezone.utc), "resolved"),
        incident("recent", "waste", 30.7335, 76.7796, datetime(2026, 10, 1, tzinfo=timezone.utc), "in_progress"),
    ]
    analysis = SimpleNamespace(severity="high")
    engine = RiskEngine()

    first = engine.calculate(target, history, analysis, cutoff)
    second = engine.calculate(target, history, analysis, cutoff)

    assert first == second
    assert 0 <= first.score <= 1
    assert 0 <= first.confidence <= 1
    assert first.factors["recurrence"] > 0


def test_route_engine_orders_stops_deterministically_and_checks_capacity():
    case = load_cases()["route"]
    first = SimpleNamespace(id="order-b", incident_id="incident-b", priority=5, estimated_volume=2.0)
    second = SimpleNamespace(id="order-a", incident_id="incident-a", priority=5, estimated_volume=2.0)
    incidents = {
        "incident-a": incident("incident-a", "a", 30.7340, 76.7794, datetime.now(timezone.utc)),
        "incident-b": incident("incident-b", "b", 30.7335, 76.7794, datetime.now(timezone.utc)),
    }

    result = RouteEngine().build([first, second], incidents, case["vehicle_capacity"], tuple(case["depot"]))
    repeat = RouteEngine().build([first, second], incidents, case["vehicle_capacity"], tuple(case["depot"]))

    assert result == repeat
    assert result.total_volume == 4
    assert result.distance_km > 0
    with pytest.raises(ValueError, match="capacity"):
        RouteEngine().build([first, second], incidents, 1, tuple(case["depot"]))