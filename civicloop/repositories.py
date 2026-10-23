from __future__ import annotations

from collections.abc import Sequence
from typing import Generic, TypeVar

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from civicloop.models import (
    AnalysisResult,
    AuditEvent,
    DuplicateCluster,
    DuplicateClusterMember,
    EvaluationRun,
    Incident,
    IncidentStatus,
    Job,
    JobStatus,
    MediaAsset,
    RiskAssessment,
    RoutePlan,
    RouteStop,
    SensorReading,
    User,
    VerificationRecord,
    WorkOrder,
    WorkOrderStatus,
)

ModelT = TypeVar("ModelT")


class BaseRepository(Generic[ModelT]):
    """Small unit-of-work repository backed by a caller-owned session."""

    model: type[ModelT]

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, entity_id: str) -> ModelT | None:
        return self.session.get(self.model, entity_id)

    def add(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        self.session.flush()
        return entity

    def update(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        self.session.flush()
        return entity

    def delete(self, entity: ModelT) -> None:
        self.session.delete(entity)
        self.session.flush()


class UserRepository(BaseRepository[User]):
    model = User

    def get_by_email(self, email: str) -> User | None:
        statement = select(User).where(User.email == email)
        return self.session.scalar(statement)

    def list_all(self, role=None, *, limit: int = 500) -> Sequence[User]:
        statement = select(User).order_by(User.created_at)
        if role is not None:
            statement = statement.where(User.role == role)
        return self.session.scalars(statement.limit(limit)).all()


class IncidentRepository(BaseRepository[Incident]):
    model = Incident

    def list_by_status(
        self, status: IncidentStatus, *, limit: int | None = None
    ) -> Sequence[Incident]:
        statement = (
            select(Incident)
            .where(Incident.status == status)
            .order_by(desc(Incident.created_at))
        )
        if limit is not None:
            statement = statement.limit(limit)
        return self.session.scalars(statement).all()

    def list_filtered(
        self,
        *,
        status: IncidentStatus | None = None,
        reporter_id: str | None = None,
        exclude_reporter_id: str | None = None,
        pincode: str | None = None,
        limit: int | None = None,
    ) -> Sequence[Incident]:
        statement = select(Incident).order_by(desc(Incident.created_at))
        if pincode is not None:
            statement = statement.where(Incident.pincode == pincode)
        if exclude_reporter_id is not None:
            statement = statement.where(Incident.reporter_id != exclude_reporter_id)
        if status is not None:
            statement = statement.where(Incident.status == status)
        if reporter_id is not None:
            statement = statement.where(Incident.reporter_id == reporter_id)
        if limit is not None:
            statement = statement.limit(limit)
        return self.session.scalars(statement).all()

    def list_for_location(
        self,
        latitude: float,
        longitude: float,
        *,
        radius_degrees: float = 0.01,
        limit: int | None = None,
    ) -> Sequence[Incident]:
        statement = (
            select(Incident)
            .where(
                Incident.latitude.between(
                    latitude - radius_degrees, latitude + radius_degrees
                )
            )
            .where(
                Incident.longitude.between(
                    longitude - radius_degrees, longitude + radius_degrees
                )
            )
            .order_by(desc(Incident.created_at))
        )
        if limit is not None:
            statement = statement.limit(limit)
        return self.session.scalars(statement).all()


class AnalysisRepository(BaseRepository[AnalysisResult]):
    model = AnalysisResult

    def list_for_incident(self, incident_id: str) -> Sequence[AnalysisResult]:
        statement = (
            select(AnalysisResult)
            .where(AnalysisResult.incident_id == incident_id)
            .order_by(desc(AnalysisResult.created_at))
        )
        return self.session.scalars(statement).all()

    def latest_for_incident(self, incident_id: str) -> AnalysisResult | None:
        statement = (
            select(AnalysisResult)
            .where(AnalysisResult.incident_id == incident_id)
            .order_by(desc(AnalysisResult.created_at))
            .limit(1)
        )
        return self.session.scalar(statement)


class RiskAssessmentRepository(BaseRepository[RiskAssessment]):
    model = RiskAssessment

    def latest_for_incident(self, incident_id: str) -> RiskAssessment | None:
        statement = (
            select(RiskAssessment)
            .where(RiskAssessment.incident_id == incident_id)
            .order_by(desc(RiskAssessment.created_at))
            .limit(1)
        )
        return self.session.scalar(statement)

    def ranked(self, *, limit: int | None = None) -> Sequence[RiskAssessment]:
        statement = select(RiskAssessment).order_by(desc(RiskAssessment.score))
        if limit is not None:
            statement = statement.limit(limit)
        return self.session.scalars(statement).all()


class WorkOrderRepository(BaseRepository[WorkOrder]):
    model = WorkOrder

    def list_by_status(self, status: WorkOrderStatus) -> Sequence[WorkOrder]:
        statement = (
            select(WorkOrder)
            .where(WorkOrder.status == status)
            .order_by(WorkOrder.priority.desc())
        )
        return self.session.scalars(statement).all()

    def list_filtered(
        self,
        *,
        status: WorkOrderStatus | None = None,
        assigned_to: str | None = None,
        limit: int = 200,
    ) -> Sequence[WorkOrder]:
        statement = select(WorkOrder).order_by(WorkOrder.priority.desc(), desc(WorkOrder.created_at))
        if status is not None:
            statement = statement.where(WorkOrder.status == status)
        if assigned_to is not None:
            statement = statement.where(WorkOrder.assigned_to == assigned_to)
        return self.session.scalars(statement.limit(limit)).all()

    def list_for_incident(self, incident_id: str) -> Sequence[WorkOrder]:
        statement = (
            select(WorkOrder)
            .where(WorkOrder.incident_id == incident_id)
            .order_by(desc(WorkOrder.created_at))
        )
        return self.session.scalars(statement).all()


class VerificationRepository(BaseRepository[VerificationRecord]):
    model = VerificationRecord

    def latest_for_incident(self, incident_id: str) -> VerificationRecord | None:
        statement = (
            select(VerificationRecord)
            .where(VerificationRecord.incident_id == incident_id)
            .order_by(desc(VerificationRecord.created_at))
            .limit(1)
        )
        return self.session.scalar(statement)


class MediaAssetRepository(BaseRepository[MediaAsset]):
    model = MediaAsset

    def list_for_incident(
        self, incident_id: str, *, after_cleanup: bool | None = None
    ) -> Sequence[MediaAsset]:
        statement = select(MediaAsset).where(MediaAsset.incident_id == incident_id)
        if after_cleanup is not None:
            statement = statement.where(MediaAsset.is_after_cleanup == after_cleanup)
        return self.session.scalars(statement.order_by(desc(MediaAsset.created_at))).all()


class DuplicateClusterRepository(BaseRepository[DuplicateCluster]):
    model = DuplicateCluster

    def add_member(self, cluster_id: str, incident_id: str, similarity_score: float) -> DuplicateClusterMember:
        member = DuplicateClusterMember(
            cluster_id=cluster_id,
            incident_id=incident_id,
            similarity_score=similarity_score,
        )
        self.session.add(member)
        self.session.flush()
        return member

    def confirm(self, cluster_id: str, user_id: str) -> DuplicateCluster:
        cluster = self.get(cluster_id)
        if cluster is None:
            raise LookupError(f"Duplicate cluster not found: {cluster_id}")
        cluster.confirmed = True
        cluster.confirmed_by = user_id
        self.session.flush()
        return cluster

    def reject(self, cluster_id: str) -> DuplicateCluster:
        cluster = self.get(cluster_id)
        if cluster is None:
            raise LookupError(f"Duplicate cluster not found: {cluster_id}")
        cluster.confirmed = False
        self.session.flush()
        return cluster

    def list_for_incident(self, incident_id: str) -> Sequence[DuplicateCluster]:
        statement = (
            select(DuplicateCluster)
            .join(DuplicateClusterMember)
            .where(DuplicateClusterMember.incident_id == incident_id)
        )
        return self.session.scalars(statement).all()


class RoutePlanRepository(BaseRepository[RoutePlan]):
    model = RoutePlan

    def add_stop(
        self, route_plan_id: str, sequence: int, work_order_id: str, planned_volume: float | None
    ) -> RouteStop:
        stop = RouteStop(
            route_plan_id=route_plan_id,
            sequence=sequence,
            work_order_id=work_order_id,
            planned_volume=planned_volume,
        )
        self.session.add(stop)
        self.session.flush()
        return stop

    def approve(self, route_plan_id: str, user_id: str) -> RoutePlan:
        plan = self.get(route_plan_id)
        if plan is None:
            raise LookupError(f"Route plan not found: {route_plan_id}")
        plan.approved_by = user_id
        self.session.flush()
        return plan

    def stops_for(self, route_plan_id: str) -> Sequence[RouteStop]:
        statement = select(RouteStop).where(RouteStop.route_plan_id == route_plan_id).order_by(RouteStop.sequence)
        return self.session.scalars(statement).all()

    def list_all(self) -> Sequence[RoutePlan]:
        return self.session.scalars(select(RoutePlan).order_by(desc(RoutePlan.created_at))).all()


class AuditEventRepository(BaseRepository[AuditEvent]):
    model = AuditEvent

    def list_for_entity(self, entity_type: str, entity_id: str) -> Sequence[AuditEvent]:
        statement = (
            select(AuditEvent)
            .where(AuditEvent.entity_type == entity_type, AuditEvent.entity_id == entity_id)
            .order_by(AuditEvent.created_at)
        )
        return self.session.scalars(statement).all()

    def list_recent(self, *, limit: int = 100, entity_type: str | None = None) -> Sequence[AuditEvent]:
        statement = select(AuditEvent).order_by(desc(AuditEvent.created_at))
        if entity_type is not None:
            statement = statement.where(AuditEvent.entity_type == entity_type)
        return self.session.scalars(statement.limit(limit)).all()

    def list_for_actor(self, actor_id: str) -> Sequence[AuditEvent]:
        statement = (
            select(AuditEvent)
            .where(AuditEvent.actor_id == actor_id)
            .order_by(AuditEvent.created_at)
        )
        return self.session.scalars(statement).all()


class EvaluationRunRepository(BaseRepository[EvaluationRun]):
    model = EvaluationRun

    def list_all(self) -> Sequence[EvaluationRun]:
        return self.session.scalars(select(EvaluationRun).order_by(desc(EvaluationRun.created_at))).all()


class SensorReadingRepository(BaseRepository[SensorReading]):
    model = SensorReading

    def latest_for_sensor(self, sensor_id: str) -> SensorReading | None:
        statement = (
            select(SensorReading)
            .where(SensorReading.sensor_id == sensor_id)
            .order_by(desc(SensorReading.observed_at))
            .limit(1)
        )
        return self.session.scalar(statement)

    def list_for_location(
        self, latitude: float, longitude: float, *, radius_degrees: float = 0.01
    ) -> Sequence[SensorReading]:
        statement = (
            select(SensorReading)
            .where(SensorReading.latitude.between(latitude - radius_degrees, latitude + radius_degrees))
            .where(SensorReading.longitude.between(longitude - radius_degrees, longitude + radius_degrees))
            .order_by(desc(SensorReading.observed_at))
        )
        return self.session.scalars(statement).all()

    def attach_incident(self, reading_id: str, incident_id: str) -> SensorReading:
        reading = self.get(reading_id)
        if reading is None:
            raise LookupError(f"Sensor reading not found: {reading_id}")
        reading.incident_id = incident_id
        self.session.flush()
        return reading


class JobRepository(BaseRepository[Job]):
    model = Job

    def get_by_idempotency_key(self, idempotency_key: str) -> Job | None:
        statement = select(Job).where(Job.idempotency_key == idempotency_key)
        return self.session.scalar(statement)

    def list_recent(self, *, status: JobStatus | None = None, limit: int = 100) -> Sequence[Job]:
        statement = select(Job).order_by(desc(Job.created_at))
        if status is not None:
            statement = statement.where(Job.status == status)
        return self.session.scalars(statement.limit(limit)).all()

    def list_by_status(self, status: JobStatus, *, limit: int = 100) -> Sequence[Job]:
        statement = select(Job).where(Job.status == status).order_by(Job.created_at).limit(limit)
        return self.session.scalars(statement).all()

    def mark_running(self, job: Job, started_at) -> Job:
        job.status = JobStatus.RUNNING
        job.attempt_count += 1
        job.started_at = started_at
        self.session.flush()
        return job

    def mark_succeeded(self, job: Job, result: dict, completed_at) -> Job:
        job.status = JobStatus.SUCCEEDED
        job.result = result
        job.completed_at = completed_at
        job.last_error_code = None
        job.last_error_message = None
        self.session.flush()
        return job

    def mark_retryable(self, job: Job, available_at, error_code: str, error_message: str) -> Job:
        job.status = JobStatus.QUEUED
        job.available_at = available_at
        job.last_error_code = error_code
        job.last_error_message = error_message
        self.session.flush()
        return job

    def mark_dead_letter(self, job: Job, completed_at, error_code: str, error_message: str) -> Job:
        job.status = JobStatus.DEAD_LETTER
        job.completed_at = completed_at
        job.last_error_code = error_code
        job.last_error_message = error_message
        self.session.flush()
        return job

    def cancel(self, job: Job) -> Job:
        job.status = JobStatus.CANCELLED
        self.session.flush()
        return job
