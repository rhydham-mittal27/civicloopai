from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from civicloop.db import create_session_factory, init_db
from civicloop.jobs import (
    InMemoryJobQueue,
    JobDispatcher,
    JobType,
    JobWorker,
    PermanentJobError,
    validate_job_payload,
)
from civicloop.job_handlers import ServiceJobHandlerFactory
from civicloop.models import AnalysisResult, Incident, IncidentStatus, ReporterType, JobStatus, MediaAsset
from civicloop.repositories import (
    AnalysisRepository,
    AuditEventRepository,
    DuplicateClusterRepository,
    EvaluationRunRepository,
    IncidentRepository,
    MediaAssetRepository,
    RiskAssessmentRepository,
    UserRepository,
    WorkOrderRepository,
    JobRepository,
)
from civicloop.services.analysis import AnalysisService
from civicloop.services.duplicate_detection import DuplicateDetectionService
from civicloop.services.hotspot_risk import HotspotRiskService
from civicloop.services.pilot import PilotService


def make_database():
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)
    return engine, create_session_factory(engine)


def test_init_db_includes_jobs_table():
    engine, _ = make_database()

    assert "jobs" in inspect(engine).get_table_names()


def test_dispatch_is_idempotent_and_worker_succeeds():
    _, session_factory = make_database()
    queue = InMemoryJobQueue()
    dispatcher = JobDispatcher(session_factory, queue)
    first = dispatcher.dispatch(JobType.ANALYZE_INCIDENT, {"incident_id": "incident-1"}, "analysis:incident-1", priority="high")
    second = dispatcher.dispatch(JobType.ANALYZE_INCIDENT, {"incident_id": "different"}, "analysis:incident-1", priority="high")

    def handlers(_session):
        return {"analyze_incident": lambda payload: {"incident_id": payload["incident_id"], "status": "ready_for_review"}}

    worker = JobWorker(session_factory, queue, handlers)
    assert first.id == second.id
    assert worker.run_once() is True

    with session_factory() as session:
        job = JobRepository(session).get(first.id)
        assert job.status == JobStatus.SUCCEEDED
        assert job.result["incident_id"] == "incident-1"


def test_high_priority_jobs_are_delivered_first():
    queue = InMemoryJobQueue()
    queue.enqueue("normal", "normal")
    queue.enqueue("high", "high")

    assert queue.dequeue().job_id == "high"
    assert queue.dequeue().job_id == "normal"


def test_permanent_failure_is_dead_lettered():
    _, session_factory = make_database()
    queue = InMemoryJobQueue()
    dispatcher = JobDispatcher(session_factory, queue)
    job = dispatcher.dispatch("unsupported", {}, "unsupported-1")

    worker = JobWorker(session_factory, queue, lambda _session: {})
    worker.run_once()

    with session_factory() as session:
        persisted = JobRepository(session).get(job.id)
        assert persisted.status == JobStatus.DEAD_LETTER
        assert queue.dead_letters


def test_cancelled_job_is_not_executed():
    _, session_factory = make_database()
    queue = InMemoryJobQueue()
    dispatcher = JobDispatcher(session_factory, queue)
    job = dispatcher.dispatch("test", {}, "cancel-1")
    dispatcher.cancel(job.id)
    called = False

    def handler(_payload):
        nonlocal called
        called = True
        return {}

    JobWorker(session_factory, queue, lambda _session: {"test": handler}).run_once()

    assert called is False


def test_payload_rejects_binary_data():
    try:
        validate_job_payload({"image": b"not-json"})
    except PermanentJobError:
        return
    raise AssertionError("Binary payload should be rejected")


def test_service_handler_factory_executes_analysis_job():
    engine, session_factory = make_database()
    with Session(engine) as session:
        incident = Incident(reporter_type=ReporterType.RESIDENT, description="Waste", latitude=1, longitude=1, occurred_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc), status=IncidentStatus.PENDING_ANALYSIS)
        IncidentRepository(session).add(incident)
        MediaAssetRepository(session).add(MediaAsset(incident_id=incident.id, storage_key="incident/image", content_type="image/jpeg", sha256="hash"))
        incident_id = incident.id
        session.commit()

    class FakeAnalysisAdapter:
        provider = "test"
        model_name = "test-model"

        def analyze(self, payload):
            return {"category": "mixed_waste", "severity": "high", "confidence": 0.9, "details": {}}

    def service_factory(session):
        users = UserRepository(session)
        incidents = IncidentRepository(session)
        assets = MediaAssetRepository(session)
        analyses = AnalysisRepository(session)
        audit = AuditEventRepository(session)
        risks = RiskAssessmentRepository(session)
        work_orders = WorkOrderRepository(session)
        return {
            "analysis": AnalysisService(analyses, incidents, assets, audit),
            "duplicates": DuplicateDetectionService(DuplicateClusterRepository(session), incidents, analyses, users, audit),
            "risk": HotspotRiskService(risks, incidents, analyses, audit),
            "pilot": PilotService(EvaluationRunRepository(session), audit, users),
        }

    queue = InMemoryJobQueue()
    dispatcher = JobDispatcher(session_factory, queue)
    worker = JobWorker(session_factory, queue, ServiceJobHandlerFactory(service_factory, analysis_adapter=FakeAnalysisAdapter))
    job = dispatcher.dispatch(JobType.ANALYZE_INCIDENT, {"incident_id": incident_id}, "handler-analysis-1")

    assert worker.run_once() is True
    with session_factory() as session:
        persisted = JobRepository(session).get(job.id)
        updated_incident = IncidentRepository(session).get(incident_id)
        assert persisted.status == JobStatus.SUCCEEDED
        assert updated_incident.status == IncidentStatus.READY_FOR_REVIEW