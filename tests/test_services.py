from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from civicloop.db import init_db
from civicloop.models import (
    IncidentStatus,
    ReporterType,
    UserRole,
    VerificationStatus,
    WorkOrderStatus,
)
from civicloop.repositories import (
    AnalysisRepository,
    AuditEventRepository,
    DuplicateClusterRepository,
    EvaluationRunRepository,
    IncidentRepository,
    MediaAssetRepository,
    RiskAssessmentRepository,
    RoutePlanRepository,
    SensorReadingRepository,
    UserRepository,
    VerificationRepository,
    WorkOrderRepository,
)
from civicloop.services.analysis import AnalysisService
from civicloop.services.audit import AuditService
from civicloop.services.duplicate_detection import DuplicateDetectionService
from civicloop.services.evaluation import EvaluationService
from civicloop.services.hotspot_risk import HotspotRiskService
from civicloop.services.incident import IncidentService
from civicloop.services.iot_integration import IoTIntegrationService
from civicloop.services.media_asset import MediaAssetService
from civicloop.services.municipal_integration import MunicipalIntegrationService
from civicloop.services.pilot import PilotService
from civicloop.services.prioritization import PrioritizationService
from civicloop.services.route_planning import RoutePlanningService
from civicloop.services.user import UserService
from civicloop.services.verification import VerificationService
from civicloop.services.work_order import WorkOrderService


class FakeAnalysisAdapter:
    provider = "test"
    model_name = "test-vision"

    def analyze(self, payload):
        assert payload["media"]
        return {"category": "mixed_waste", "severity": "high", "confidence": 0.95, "details": {"bags": 4}}


class FakeRoutingAdapter:
    def plan(self, stops, vehicle_capacity, constraints):
        return {"distance_km": 4.5, "duration_minutes": 18.0}

    def baseline(self, stops):
        return {"distance_km": 6.0}


class FakeMunicipalAdapter:
    def export_work_orders(self, payload):
        return {"accepted": len(payload)}

    def import_status_updates(self, updates):
        return updates


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)
    with Session(engine) as database_session:
        yield database_session


@pytest.fixture
def services(session):
    users = UserRepository(session)
    incidents = IncidentRepository(session)
    assets = MediaAssetRepository(session)
    analyses = AnalysisRepository(session)
    clusters = DuplicateClusterRepository(session)
    risks = RiskAssessmentRepository(session)
    work_orders = WorkOrderRepository(session)
    routes = RoutePlanRepository(session)
    verifications = VerificationRepository(session)
    audit_events = AuditEventRepository(session)
    evaluations = EvaluationRunRepository(session)
    readings = SensorReadingRepository(session)
    audit = AuditService(audit_events)
    return {
        "users": UserService(users, audit_events),
        "incidents": IncidentService(incidents, users, audit_events),
        "media": MediaAssetService(assets, incidents, users, audit_events),
        "analysis": AnalysisService(analyses, incidents, assets, audit_events),
        "duplicates": DuplicateDetectionService(clusters, incidents, analyses, users, audit_events),
        "risk": HotspotRiskService(risks, incidents, analyses, audit_events),
        "priority": PrioritizationService(risks, incidents, work_orders, users, audit_events),
        "orders": WorkOrderService(work_orders, incidents, users, audit_events),
        "routes": RoutePlanningService(routes, work_orders, incidents, users, audit_events),
        "verification": VerificationService(verifications, assets, incidents, users, audit_events),
        "audit": audit,
        "evaluation": EvaluationService(evaluations, audit_events),
        "pilot": PilotService(evaluations, audit_events, users),
        "municipal": MunicipalIntegrationService(work_orders, users, audit_events),
        "iot": IoTIntegrationService(readings, incidents, audit_events),
    }


def create_users(services):
    user_service = services["users"]
    reporter = user_service.create_user("Reporter", "reporter@example.com", UserRole.REPORTER)
    supervisor = user_service.create_user("Supervisor", "supervisor@example.com", UserRole.SUPERVISOR)
    worker = user_service.create_user("Worker", "worker@example.com", UserRole.SANITATION_WORKER)
    return reporter, supervisor, worker


def create_incident(services, reporter_id):
    return services["incidents"].create_incident(
        reporter_id=reporter_id,
        reporter_type=ReporterType.RESIDENT,
        description="Waste near the market",
        latitude=30.7333,
        longitude=76.7794,
        occurred_at=datetime.now(timezone.utc),
    )


def test_report_media_analysis_and_risk_workflow(services):
    reporter, _, _ = create_users(services)
    incident = create_incident(services, reporter.id)
    asset = services["media"].store_for_incident(incident.id, b"before-image")
    result = services["analysis"].analyze_incident(incident.id, FakeAnalysisAdapter())
    risk = services["risk"].calculate_risk(incident.id)

    assert asset.is_after_cleanup is False
    assert result.category == "mixed_waste"
    assert incident.status == IncidentStatus.READY_FOR_REVIEW
    assert risk.score > 0


def test_duplicate_priority_work_order_route_and_verification_workflow(services):
    reporter, supervisor, worker = create_users(services)
    incident = create_incident(services, reporter.id)
    services["media"].store_for_incident(incident.id, b"before-image")
    services["analysis"].analyze_incident(incident.id, FakeAnalysisAdapter())
    services["risk"].calculate_risk(incident.id)
    cluster = services["duplicates"].create_candidate_cluster(incident.id, [])
    services["duplicates"].confirm_cluster(cluster.id, supervisor.id)
    order = services["orders"].create_order(incident.id, priority=10, estimated_volume=2.0, actor_id=supervisor.id)
    services["orders"].approve_order(order.id, supervisor.id)
    services["orders"].assign_order(order.id, worker.id, supervisor.id)
    plan = services["routes"].build_route([order.id], 10.0, {}, supervisor.id, FakeRoutingAdapter())
    services["routes"].approve_route(plan.id, supervisor.id)
    completed = services["orders"].complete_order(order.id, worker.id)
    verification = services["verification"].submit_evidence(incident.id, worker.id, b"after-image")

    assert cluster.confirmed is True
    assert plan.baseline_distance_km == 6.0
    assert completed.status == WorkOrderStatus.COMPLETED
    assert verification.status == VerificationStatus.VERIFIED
    assert incident.status == IncidentStatus.VERIFIED


def test_audit_evaluation_pilot_and_integrations(services):
    _, supervisor, _ = create_users(services)
    run = services["evaluation"].run_evaluation(
        "sample-v1",
        "smoke-test",
        {"verified_closure": lambda: 1.0},
        {"verified_closure": 0.5},
    )
    comparison = services["evaluation"].compare_with_baseline(run.id)
    pilot = services["pilot"].start_pilot("Chandigarh", "Chandigarh", date(2026, 1, 1), date(2026, 3, 1), "sample-v1", supervisor.id)
    services["pilot"].collect_metrics(pilot.id, {"resolution_time": 12})
    export = services["municipal"].export_work_orders([], "municipal-test", supervisor.id, FakeMunicipalAdapter())
    reading = services["iot"].ingest_reading("sensor-1", 30.7333, 76.7794, {"fill_level": 0.8}, datetime.now(timezone.utc))
    history = services["audit"].history("evaluation_run", run.id)

    assert comparison["verified_closure"]["baseline"] == 0.5
    assert pilot.metrics["resolution_time"] == 12
    assert export == {"accepted": 0}
    assert reading.sensor_id == "sensor-1"
    assert len(history) == 1


def test_services_reject_unauthorized_actions(services):
    reporter, supervisor, worker = create_users(services)
    incident = create_incident(services, reporter.id)

    with pytest.raises(Exception):
        services["orders"].create_order(incident.id, 1, 1.0, reporter.id)

    services["media"].store_for_incident(incident.id, b"before-image")
    services["analysis"].analyze_incident(incident.id, FakeAnalysisAdapter())
    with pytest.raises(ValueError, match="not waiting for analysis"):
        services["analysis"].analyze_incident(incident.id, FakeAnalysisAdapter())

    with pytest.raises(ValueError, match="Before-cleanup evidence"):
        new_incident = create_incident(services, reporter.id)
        services["verification"].submit_evidence(new_incident.id, worker.id, b"after-image")