from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from civicloop.db import Base


def new_id() -> str:
    return str(uuid.uuid4())


class IncidentStatus(str, enum.Enum):
    PENDING_ANALYSIS = "pending_analysis"
    READY_FOR_REVIEW = "ready_for_review"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    VERIFIED = "verified"
    UNCERTAIN = "uncertain"
    REJECTED = "rejected"


class ReporterType(str, enum.Enum):
    RESIDENT = "resident"
    FIELD_WORKER = "field_worker"
    SUPERVISOR = "supervisor"


class UserRole(str, enum.Enum):
    REPORTER = "reporter"
    SUPERVISOR = "supervisor"
    SANITATION_WORKER = "sanitation_worker"
    ADMIN = "admin"


class WorkOrderStatus(str, enum.Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class VerificationStatus(str, enum.Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    UNCERTAIN = "uncertain"
    REJECTED = "rejected"


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"
    CANCELLED = "cancelled"


class Tenant(Base):
    """A city (or other municipal body) whose data is kept apart from every other tenant's."""

    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(150))
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    state: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Cities opened by self-registration start unverified: they work, but stay out of the public
    # suggestions until a platform admin confirms the name (or merges a typo into the real city).
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TenantScoped:
    """Mixin for every row that belongs to one city.

    `tenant_id` is filled in and enforced centrally (see civicloop.tenancy), so repositories and
    routes never have to remember to filter on it.
    """

    @declared_attr
    def tenant_id(cls) -> Mapped[str]:
        return mapped_column(ForeignKey("tenants.id"), index=True)


class User(TenantScoped, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    pincode: Mapped[str | None] = mapped_column(String(6), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    incidents: Mapped[list[Incident]] = relationship(back_populates="reporter")


class Incident(TenantScoped, Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    reporter_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    reporter_type: Mapped[ReporterType] = mapped_column(Enum(ReporterType))
    description: Mapped[str] = mapped_column(Text)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    pincode: Mapped[str | None] = mapped_column(String(6), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus), default=IncidentStatus.PENDING_ANALYSIS, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    reporter: Mapped[User | None] = relationship(back_populates="incidents")
    media_assets: Mapped[list[MediaAsset]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )
    analyses: Mapped[list[AnalysisResult]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )
    risk_assessments: Mapped[list[RiskAssessment]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )
    work_orders: Mapped[list[WorkOrder]] = relationship(back_populates="incident")
    verification_records: Mapped[list[VerificationRecord]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )
    sensor_readings: Mapped[list[SensorReading]] = relationship(
        back_populates="incident"
    )


class MediaAsset(TenantScoped, Base):
    __tablename__ = "media_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    content_type: Mapped[str] = mapped_column(String(100))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_after_cleanup: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    incident: Mapped[Incident] = relationship(back_populates="media_assets")


class AnalysisResult(TenantScoped, Base):
    __tablename__ = "analysis_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    provider: Mapped[str] = mapped_column(String(100))
    model_name: Mapped[str] = mapped_column(String(150))
    category: Mapped[str | None] = mapped_column(String(100))
    severity: Mapped[str | None] = mapped_column(String(50))
    confidence: Mapped[float | None] = mapped_column(Float)
    extracted_details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    raw_response: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    incident: Mapped[Incident] = relationship(back_populates="analyses")


class DuplicateCluster(TenantScoped, Base):
    __tablename__ = "duplicate_clusters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    label: Mapped[str | None] = mapped_column(String(200))
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    confirmed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    members: Mapped[list[DuplicateClusterMember]] = relationship(
        back_populates="cluster", cascade="all, delete-orphan"
    )


class DuplicateClusterMember(TenantScoped, Base):
    __tablename__ = "duplicate_cluster_members"

    cluster_id: Mapped[str] = mapped_column(
        ForeignKey("duplicate_clusters.id", ondelete="CASCADE"), primary_key=True
    )
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), primary_key=True
    )
    similarity_score: Mapped[float | None] = mapped_column(Float)

    cluster: Mapped[DuplicateCluster] = relationship(back_populates="members")


class RiskAssessment(TenantScoped, Base):
    __tablename__ = "risk_assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    score: Mapped[float] = mapped_column(Float, index=True)
    confidence: Mapped[float | None] = mapped_column(Float)
    factors: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    model_version: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    incident: Mapped[Incident] = relationship(back_populates="risk_assessments")


class WorkOrder(TenantScoped, Base):
    __tablename__ = "work_orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    assigned_to: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[WorkOrderStatus] = mapped_column(
        Enum(WorkOrderStatus), default=WorkOrderStatus.DRAFT, index=True
    )
    priority: Mapped[int] = mapped_column(Integer, default=0, index=True)
    estimated_volume: Mapped[float | None] = mapped_column(Float)
    override_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    incident: Mapped[Incident] = relationship(back_populates="work_orders")
    route_stops: Mapped[list[RouteStop]] = relationship(back_populates="work_order")


class RoutePlan(TenantScoped, Base):
    __tablename__ = "route_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    vehicle_capacity: Mapped[float] = mapped_column(Float)
    estimated_distance_km: Mapped[float | None] = mapped_column(Float)
    estimated_duration_minutes: Mapped[float | None] = mapped_column(Float)
    baseline_distance_km: Mapped[float | None] = mapped_column(Float)
    constraints: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    stops: Mapped[list[RouteStop]] = relationship(
        back_populates="route_plan", cascade="all, delete-orphan"
    )


class RouteStop(TenantScoped, Base):
    __tablename__ = "route_stops"

    route_plan_id: Mapped[str] = mapped_column(
        ForeignKey("route_plans.id", ondelete="CASCADE"), primary_key=True
    )
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_order_id: Mapped[str] = mapped_column(ForeignKey("work_orders.id"), index=True)
    planned_volume: Mapped[float | None] = mapped_column(Float)

    route_plan: Mapped[RoutePlan] = relationship(back_populates="stops")
    work_order: Mapped[WorkOrder] = relationship(back_populates="route_stops")


class VerificationRecord(TenantScoped, Base):
    __tablename__ = "verification_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    submitted_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus), default=VerificationStatus.PENDING, index=True
    )
    evidence_notes: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    review_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    incident: Mapped[Incident] = relationship(back_populates="verification_records")


class AuditEvent(TenantScoped, Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    entity_type: Mapped[str] = mapped_column(String(100), index=True)
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(100))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class EvaluationRun(TenantScoped, Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    dataset_version: Mapped[str] = mapped_column(String(100))
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    baseline_metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SensorReading(TenantScoped, Base):
    __tablename__ = "sensor_readings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    sensor_id: Mapped[str] = mapped_column(String(150), index=True)
    incident_id: Mapped[str | None] = mapped_column(
        ForeignKey("incidents.id"), index=True
    )
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    reading: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    incident: Mapped[Incident | None] = relationship(back_populates="sensor_readings")


class Job(TenantScoped, Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_type: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus), default=JobStatus.QUEUED, index=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Vehicle(TenantScoped, Base):
    """A collection vehicle whose position is tracked, from a crew phone or a GPS tracker."""

    __tablename__ = "vehicles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    label: Mapped[str] = mapped_column(String(80))
    registration: Mapped[str | None] = mapped_column(String(40))
    driver_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    # Only a hash is stored. A tracker sends the key itself, and it is shown once when issued.
    device_key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # The latest fix is kept on the vehicle so the live map never scans the history.
    last_lat: Mapped[float | None] = mapped_column(Float)
    last_lon: Mapped[float | None] = mapped_column(Float)
    last_speed_kmh: Mapped[float | None] = mapped_column(Float)
    last_heading: Mapped[float | None] = mapped_column(Float)
    last_accuracy_m: Mapped[float | None] = mapped_column(Float)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_source: Mapped[str | None] = mapped_column(String(20))
    # Distance driven on the current (Indian) calendar day, kept as a running total.
    day_key: Mapped[str | None] = mapped_column(String(10))
    day_distance_km: Mapped[float | None] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class VehiclePing(TenantScoped, Base):
    """One GPS fix in a vehicle's history."""

    __tablename__ = "vehicle_pings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    vehicle_id: Mapped[str] = mapped_column(ForeignKey("vehicles.id", ondelete="CASCADE"), index=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    speed_kmh: Mapped[float | None] = mapped_column(Float)
    heading: Mapped[float | None] = mapped_column(Float)
    accuracy_m: Mapped[float | None] = mapped_column(Float)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    source: Mapped[str] = mapped_column(String(20), default="device")
