"""Operational API: risk, queue, duplicates, work orders, routes, verification and the admin tools.

Every route states which roles may call it. The frontend mirrors this table, but the server
is the authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from civicloop.auth import AuthPrincipal
from civicloop.container import build_services
from civicloop.jobs import JobDispatcher
from civicloop.models import (
    AnalysisResult,
    AuditEvent,
    Incident,
    IncidentStatus,
    Job,
    JobStatus,
    MediaAsset,
    RoutePlan,
    SensorReading,
    Tenant,
    TenantScoped,
    User,
    UserRole,
    VerificationRecord,
    VerificationStatus,
    WorkOrder,
    WorkOrderStatus,
)
from civicloop.db import Base
from civicloop.services.common import record_audit
from civicloop.synthetic import SYNTHETIC_LIKE
from civicloop.tenancy import bind_tenant, normalise_city, slugify
from civicloop.services.municipal_integration import ManualMunicipalAdapter
from civicloop.storage import ObjectStorageAdapter, StorageObjectNotFound

SUPERVISOR = {UserRole.SUPERVISOR, UserRole.ADMIN}
STAFF = {UserRole.SUPERVISOR, UserRole.ADMIN, UserRole.SANITATION_WORKER}
ADMIN = {UserRole.ADMIN}
WORKER = {UserRole.SANITATION_WORKER}
MAX_IMAGE_BYTES = 10 * 1024 * 1024


@dataclass
class Ctx:
    get_session: Callable[..., Any]
    principal: Callable[..., AuthPrincipal]
    storage: ObjectStorageAdapter
    dispatcher: JobDispatcher
    system: dict[str, Any]


# ---------------------------------------------------------------- serialisers


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def incident_dict(i: Incident) -> dict[str, Any]:
    return {
        "id": i.id,
        "reporter_id": i.reporter_id,
        "reporter_type": i.reporter_type.value,
        "description": i.description,
        "latitude": i.latitude,
        "longitude": i.longitude,
        "pincode": i.pincode,
        "occurred_at": _iso(i.occurred_at),
        "status": i.status.value,
    }


def risk_dict(r: Any) -> dict[str, Any] | None:
    if r is None:
        return None
    raw = r.factors or {}
    factors = {k: v for k, v in raw.items() if not k.startswith("_") and k != "cutoff_at"}
    learned = r.model_version.startswith(("risk-gbm", "risk-logit"))
    return {
        "id": r.id,
        "incident_id": r.incident_id,
        "score": r.score,
        "confidence": r.confidence,
        "factors": factors,
        "kind": "probability" if learned else "formula",
        "method": raw.get("_method", "hand-set formula"),
        "contributions": raw.get("_contributions", {}),
        "model_version": r.model_version,
        "created_at": _iso(r.created_at),
    }


def order_dict(o: WorkOrder, incident: Incident | None = None, users: dict[str, str] | None = None) -> dict[str, Any]:
    names = users or {}
    return {
        "id": o.id,
        "incident_id": o.incident_id,
        "status": o.status.value,
        "priority": o.priority,
        "estimated_volume": o.estimated_volume,
        "override_reason": o.override_reason,
        "approved_by": o.approved_by,
        "assigned_to": o.assigned_to,
        "assigned_to_name": names.get(o.assigned_to or ""),
        "created_at": _iso(o.created_at),
        "incident": incident_dict(incident) if incident else None,
    }


def analysis_dict(a: AnalysisResult | None) -> dict[str, Any] | None:
    if a is None:
        return None
    return {
        "id": a.id,
        "incident_id": a.incident_id,
        "provider": a.provider,
        "model_name": a.model_name,
        "category": a.category,
        "severity": a.severity,
        "confidence": a.confidence,
        "details": a.extracted_details or {},
        "created_at": _iso(a.created_at),
    }


def verification_dict(v: VerificationRecord | None) -> dict[str, Any] | None:
    if v is None:
        return None
    return {
        "id": v.id,
        "incident_id": v.incident_id,
        "status": v.status.value,
        "evidence_notes": v.evidence_notes,
        "submitted_by": v.submitted_by,
        "reviewed_by": v.reviewed_by,
        "review_reason": v.review_reason,
        "created_at": _iso(v.created_at),
        "reviewed_at": _iso(v.reviewed_at),
    }


def media_dict(m: MediaAsset) -> dict[str, Any]:
    return {
        "id": m.id,
        "storage_key": m.storage_key,
        "content_type": m.content_type,
        "sha256": m.sha256,
        "is_after_cleanup": m.is_after_cleanup,
    }


def user_dict(u: User) -> dict[str, Any]:
    return {
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "role": u.role.value,
        "is_active": u.is_active,
        "pincode": u.pincode,
        "created_at": _iso(u.created_at),
    }


def job_dict(j: Job) -> dict[str, Any]:
    return {
        "id": j.id,
        "job_type": j.job_type,
        "status": j.status.value,
        "result": j.result,
        "attempt_count": j.attempt_count,
        "max_attempts": j.max_attempts,
        "last_error_code": j.last_error_code,
        "last_error_message": j.last_error_message,
        "created_at": _iso(j.created_at),
        "completed_at": _iso(j.completed_at),
    }


def reading_dict(r: SensorReading) -> dict[str, Any]:
    return {
        "id": r.id,
        "sensor_id": r.sensor_id,
        "incident_id": r.incident_id,
        "latitude": r.latitude,
        "longitude": r.longitude,
        "reading": r.reading,
        "observed_at": _iso(r.observed_at),
    }


def run_dict(run: Any) -> dict[str, Any]:
    return {
        "id": run.id,
        "name": run.name,
        "dataset_version": run.dataset_version,
        "metrics": run.metrics or {},
        "baseline_metrics": run.baseline_metrics or {},
        "created_at": _iso(run.created_at),
    }


# ---------------------------------------------------------------- requests


class WorkOrderCreate(BaseModel):
    priority: int = Field(default=5, ge=0, le=100)
    estimated_volume: float | None = Field(default=None, ge=0)


class AssignRequest(BaseModel):
    worker_id: str


class ReasonRequest(BaseModel):
    reason: str = Field(min_length=1)


class OverrideRequest(BaseModel):
    priority: int = Field(ge=0, le=100)
    reason: str = Field(min_length=1)


class ClusterRequest(BaseModel):
    candidate_ids: list[str] = Field(min_length=1)


class RouteCreate(BaseModel):
    work_order_ids: list[str] = Field(min_length=1)
    vehicle_capacity: float = Field(gt=0)
    depot_latitude: float | None = Field(default=None, ge=-90, le=90)
    depot_longitude: float | None = Field(default=None, ge=-180, le=180)
    max_duration_minutes: float | None = Field(default=None, gt=0, le=1440)


class ReviewRequest(BaseModel):
    status: VerificationStatus
    reason: str = Field(min_length=1)


class CityPatch(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=100)
    verified: bool | None = None
    is_active: bool | None = None


class CityMerge(BaseModel):
    into_id: str


class UserPatch(BaseModel):
    role: UserRole | None = None
    is_active: bool | None = None


class PilotCreate(BaseModel):
    name: str = Field(min_length=1)
    location: str = Field(min_length=1)
    start_date: date
    end_date: date
    baseline_version: str = Field(min_length=1)


class PilotMetrics(BaseModel):
    metrics: dict[str, float | int | str] = Field(min_length=1)


class SensorReadingCreate(BaseModel):
    sensor_id: str = Field(min_length=1, max_length=150)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    reading: dict[str, float | int | str | bool] = Field(min_length=1)
    observed_at: datetime | None = None


class AssociateRequest(BaseModel):
    incident_id: str


class MunicipalExport(BaseModel):
    work_order_ids: list[str] = Field(min_length=1)
    system_name: str = Field(min_length=1, default="municipal")


class StatusUpdate(BaseModel):
    work_order_id: str
    status: WorkOrderStatus


class MunicipalImport(BaseModel):
    updates: list[StatusUpdate] = Field(min_length=1)
    system_name: str = Field(min_length=1, default="municipal")


class EvaluationRequest(BaseModel):
    name: str = Field(min_length=1, default="System snapshot")
    dataset_version: str = Field(min_length=1, default="live")


# ---------------------------------------------------------------- router


def build_ops_router(ctx: Ctx) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    def allow(*roles: UserRole):
        allowed = set(roles)

        def dependency(principal: AuthPrincipal = Depends(ctx.principal)) -> AuthPrincipal:
            if principal.role not in allowed:
                raise HTTPException(status_code=403, detail="Your role cannot do this")
            return principal

        return dependency

    def svc(session: Session) -> dict[str, Any]:
        return build_services(session, ctx.storage)

    def names(session: Session, ids: set[str | None]) -> dict[str, str]:
        wanted = {i for i in ids if i}
        if not wanted:
            return {}
        rows = session.execute(select(User.id, User.name).where(User.id.in_(wanted))).all()
        return {row[0]: row[1] for row in rows}

    def get_incident_for(session: Session, incident_id: str, principal: AuthPrincipal) -> Incident:
        incident = session.get(Incident, incident_id)
        if incident is None:
            raise HTTPException(status_code=404, detail="Incident not found")
        if principal.role == UserRole.REPORTER and incident.reporter_id != principal.user_id:
            raise HTTPException(status_code=404, detail="Incident not found")
        return incident

    S = Depends(ctx.get_session)

    # ----------------------------------------------------------- identity & admin

    @router.get("/auth/me")
    def me(principal: AuthPrincipal = Depends(ctx.principal), session: Session = S) -> dict[str, Any]:
        bind_tenant(session, None)  # a platform admin may be viewing another city; their own row lives in their home one
        user = session.get(User, principal.user_id)
        home = session.get(Tenant, user.tenant_id)
        active = session.get(Tenant, principal.tenant_id)
        bind_tenant(session, principal.tenant_id)
        return {
            **user_dict(user),
            "city": active.name,
            "state": active.state,
            "tenant_id": active.id,
            "city_verified": active.verified,
            "home_city": home.name,
            "is_platform_admin": principal.is_platform_admin,
        }

    # ----------------------------------------------------------- platform (across cities)

    def platform(principal: AuthPrincipal = Depends(ctx.principal), session: Session = S) -> AuthPrincipal:
        if not principal.is_platform_admin:
            raise HTTPException(status_code=403, detail="Platform administrators only")
        bind_tenant(session, None)  # these routes look across every city
        return principal

    def city_row(session: Session, t: Tenant) -> dict[str, Any]:
        simulated = select(User.id).where(User.email.like(SYNTHETIC_LIKE), User.tenant_id == t.id)

        def count(model: Any) -> int:
            where = [model.tenant_id == t.id]
            if model is User:
                where.append(User.email.not_like(SYNTHETIC_LIKE))
            if model is Incident:
                where.append(Incident.reporter_id.not_in(simulated))  # the simulated training history is not real reports
            return session.scalar(select(func.count()).select_from(model).where(*where)) or 0

        return {
            "id": t.id,
            "name": t.name,
            "slug": t.slug,
            "state": t.state,
            "verified": t.verified,
            "is_active": t.is_active,
            "users": count(User),
            "incidents": count(Incident),
            "created_at": _iso(t.created_at),
        }

    @router.get("/platform/cities")
    def platform_cities(principal: AuthPrincipal = Depends(platform), session: Session = S) -> list[dict[str, Any]]:
        return [city_row(session, t) for t in session.scalars(select(Tenant).order_by(Tenant.name))]

    @router.patch("/platform/cities/{city_id}")
    def platform_patch_city(city_id: str, payload: CityPatch, principal: AuthPrincipal = Depends(platform), session: Session = S):
        city = session.get(Tenant, city_id)
        if city is None:
            raise HTTPException(status_code=404, detail="City not found")
        if payload.is_active is False and city.id == principal.tenant_id:
            raise HTTPException(status_code=400, detail="You cannot disable the city you are signed in to")
        changes: dict[str, Any] = {}
        if payload.name is not None and payload.name.strip():
            clean = normalise_city(payload.name)
            slug = slugify(clean)
            clash = session.scalar(select(Tenant).where(Tenant.slug == slug, Tenant.id != city.id))
            if clash is not None:
                raise HTTPException(status_code=409, detail=f"{clash.name} already exists. Merge into it instead.")
            changes["name"] = clean
            city.name, city.slug = clean, slug
        for field in ("state", "verified", "is_active"):
            value = getattr(payload, field)
            if value is not None and value != getattr(city, field):
                changes[field] = value
                setattr(city, field, value)
        if changes:
            record_audit(svc(session)["audit_repo"], principal.user_id, "tenant", city.id, "updated", changes)
        session.commit()
        return city_row(session, city)

    @router.post("/platform/cities/{city_id}/merge")
    def platform_merge_city(city_id: str, payload: CityMerge, principal: AuthPrincipal = Depends(platform), session: Session = S):
        """Fold a misspelt city into the real one: everything it holds moves, then it is removed."""
        source, target = session.get(Tenant, city_id), session.get(Tenant, payload.into_id)
        if source is None or target is None:
            raise HTTPException(status_code=404, detail="City not found")
        if source.id == target.id:
            raise HTTPException(status_code=400, detail="Choose a different city to merge into")
        if principal.tenant_id == source.id:
            raise HTTPException(status_code=400, detail="You cannot merge the city you are signed in to")
        moved = 0
        for mapper in Base.registry.mappers:
            model = mapper.class_
            if issubclass(model, TenantScoped):
                moved += session.execute(update(model).where(model.tenant_id == source.id).values(tenant_id=target.id)).rowcount or 0
        session.expire_all()  # rows moved underneath loaded objects (including the caller's own)
        record_audit(svc(session)["audit_repo"], principal.user_id, "tenant", target.id, "merged", {"from": source.name, "rows_moved": moved})
        session.delete(source)
        session.commit()
        return city_row(session, target)

    @router.get("/me/badges")
    def my_badges(principal: AuthPrincipal = Depends(ctx.principal), session: Session = S) -> dict[str, int]:
        """Small counts for the sidebar: what is waiting for this person."""
        def count(model: Any, *where: Any) -> int:
            return session.scalar(select(func.count()).select_from(model).where(*where)) or 0

        if principal.role in SUPERVISOR:
            return {
                "incidents": count(Incident, Incident.status == IncidentStatus.READY_FOR_REVIEW),
                "work": count(WorkOrder, WorkOrder.status == WorkOrderStatus.APPROVED),
                "routes": count(RoutePlan, RoutePlan.approved_by.is_(None)),
            }
        if principal.role == UserRole.SANITATION_WORKER:
            return {
                "work": count(
                    WorkOrder,
                    WorkOrder.assigned_to == principal.user_id,
                    WorkOrder.status.in_([WorkOrderStatus.ASSIGNED, WorkOrderStatus.IN_PROGRESS]),
                )
            }
        closed = [IncidentStatus.VERIFIED, IncidentStatus.REJECTED]
        return {"incidents": count(Incident, Incident.reporter_id == principal.user_id, Incident.status.not_in(closed))}

    @router.get("/users")
    def list_users(
        role: UserRole | None = None,
        principal: AuthPrincipal = Depends(allow(UserRole.ADMIN, UserRole.SUPERVISOR)),
        session: Session = S,
    ) -> list[dict[str, Any]]:
        if principal.role == UserRole.SUPERVISOR and role != UserRole.SANITATION_WORKER:
            raise HTTPException(status_code=403, detail="Supervisors can only list sanitation workers")
        return [user_dict(u) for u in svc(session)["users_repo"].list_all(role)]

    @router.patch("/users/{user_id}")
    def patch_user(
        user_id: str,
        payload: UserPatch,
        principal: AuthPrincipal = Depends(allow(UserRole.ADMIN)),
        session: Session = S,
    ) -> dict[str, Any]:
        user = session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        if user.id == principal.user_id and (payload.role not in (None, user.role) or payload.is_active is False):
            raise HTTPException(status_code=400, detail="You cannot change your own role or deactivate yourself")
        services = svc(session)
        details: dict[str, Any] = {}
        if payload.role is not None and payload.role != user.role:
            details["role"] = {"from": user.role.value, "to": payload.role.value}
            user.role = payload.role
        if payload.is_active is not None and payload.is_active != user.is_active:
            details["is_active"] = payload.is_active
            user.is_active = payload.is_active
        if details:
            from civicloop.services.common import record_audit

            record_audit(services["audit_repo"], principal.user_id, "user", user.id, "updated", details)
        session.commit()
        return user_dict(user)

    @router.get("/audit")
    def audit_log(
        entity_type: str | None = None,
        limit: int = 100,
        principal: AuthPrincipal = Depends(allow(UserRole.ADMIN, UserRole.SUPERVISOR)),
        session: Session = S,
    ) -> list[dict[str, Any]]:
        events = svc(session)["audit_repo"].list_recent(limit=min(limit, 500), entity_type=entity_type)
        who = names(session, {e.actor_id for e in events})
        return [
            {
                "id": e.id,
                "actor_id": e.actor_id,
                "actor_name": who.get(e.actor_id or "", "System"),
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "action": e.action,
                "details": e.details or {},
                "created_at": _iso(e.created_at),
            }
            for e in events
        ]

    @router.get("/system/status")
    def system_status(principal: AuthPrincipal = Depends(allow(*STAFF)), session: Session = S) -> dict[str, Any]:
        queued = session.scalar(select(func.count()).select_from(Job).where(Job.status == JobStatus.QUEUED)) or 0
        return {**ctx.system, "jobs_queued": queued}

    # ----------------------------------------------------------- jobs

    @router.get("/jobs")
    def list_jobs(
        status: JobStatus | None = None,
        limit: int = 100,
        principal: AuthPrincipal = Depends(allow(UserRole.ADMIN)),
        session: Session = S,
    ) -> list[dict[str, Any]]:
        return [job_dict(j) for j in svc(session)["jobs_repo"].list_recent(status=status, limit=min(limit, 300))]

    @router.post("/jobs/{job_id}/retry")
    def retry_job(job_id: str, principal: AuthPrincipal = Depends(allow(UserRole.ADMIN))) -> dict[str, Any]:
        try:
            return job_dict(ctx.dispatcher.retry(job_id, tenant_id=principal.tenant_id))
        except LookupError as error:
            raise HTTPException(status_code=404, detail="Job not found") from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.post("/jobs/{job_id}/cancel")
    def cancel_job(job_id: str, principal: AuthPrincipal = Depends(allow(UserRole.ADMIN))) -> dict[str, Any]:
        try:
            return job_dict(ctx.dispatcher.cancel(job_id, tenant_id=principal.tenant_id))
        except LookupError as error:
            raise HTTPException(status_code=404, detail="Job not found") from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    # ----------------------------------------------------------- incident detail extras

    @router.get("/incidents/{incident_id}/analysis")
    def latest_analysis(incident_id: str, principal: AuthPrincipal = Depends(ctx.principal), session: Session = S):
        get_incident_for(session, incident_id, principal)
        return analysis_dict(svc(session)["analysis"].latest_analysis(incident_id))

    @router.get("/incidents/{incident_id}/risk")
    def latest_risk(incident_id: str, principal: AuthPrincipal = Depends(allow(*STAFF)), session: Session = S):
        get_incident_for(session, incident_id, principal)
        return risk_dict(svc(session)["risk"].latest_risk(incident_id))

    @router.post("/incidents/{incident_id}/risk")
    def calculate_risk(incident_id: str, principal: AuthPrincipal = Depends(allow(*SUPERVISOR)), session: Session = S):
        get_incident_for(session, incident_id, principal)
        result = svc(session)["risk"].calculate_risk(incident_id)
        session.commit()
        return risk_dict(result)

    @router.get("/incidents/{incident_id}/timeline")
    def timeline(incident_id: str, principal: AuthPrincipal = Depends(allow(*STAFF)), session: Session = S):
        get_incident_for(session, incident_id, principal)
        services = svc(session)
        audit = services["audit_repo"]
        events = list(audit.list_for_entity("incident", incident_id))
        for order in services["orders_repo"].list_for_incident(incident_id):
            events += audit.list_for_entity("work_order", order.id)
        for record in session.scalars(select(VerificationRecord).where(VerificationRecord.incident_id == incident_id)):
            events += audit.list_for_entity("verification", record.id)
        events.sort(key=lambda e: e.created_at)
        who = names(session, {e.actor_id for e in events})
        return [
            {
                "id": e.id,
                "action": e.action,
                "entity_type": e.entity_type,
                "actor_name": who.get(e.actor_id or "", "System"),
                "details": e.details or {},
                "created_at": _iso(e.created_at),
            }
            for e in events
        ]

    @router.get("/incidents/{incident_id}/sensors")
    def incident_sensors(incident_id: str, principal: AuthPrincipal = Depends(allow(*SUPERVISOR)), session: Session = S):
        incident = get_incident_for(session, incident_id, principal)
        readings = svc(session)["readings_repo"].list_for_location(incident.latitude, incident.longitude)
        return [reading_dict(r) for r in readings[:20]]

    @router.post("/incidents/{incident_id}/override")
    def override_priority(
        incident_id: str,
        payload: OverrideRequest,
        principal: AuthPrincipal = Depends(allow(*SUPERVISOR)),
        session: Session = S,
    ):
        order = svc(session)["priority"].apply_override(incident_id, principal.user_id, payload.priority, payload.reason)
        session.commit()
        return order_dict(order)

    # ----------------------------------------------------------- duplicates

    def cluster_dict(session: Session, cluster: Any) -> dict[str, Any]:
        members = []
        for member in cluster.members:
            incident = session.get(Incident, member.incident_id)
            members.append(
                {
                    "incident_id": member.incident_id,
                    "similarity_score": member.similarity_score,
                    "description": incident.description if incident else "",
                    "status": incident.status.value if incident else None,
                }
            )
        return {"id": cluster.id, "confirmed": cluster.confirmed, "members": members, "created_at": _iso(cluster.created_at)}

    @router.get("/incidents/{incident_id}/duplicates")
    def duplicates(incident_id: str, principal: AuthPrincipal = Depends(allow(*SUPERVISOR)), session: Session = S):
        get_incident_for(session, incident_id, principal)
        services = svc(session)
        grouped = {m["incident_id"] for c in services["clusters_repo"].list_for_incident(incident_id) for m in cluster_dict(session, c)["members"]}
        candidates = []
        method = None
        for match in services["duplicates"].find_matches(incident_id):
            other = session.get(Incident, match.incident_id)
            method = match.text_method
            candidates.append(
                {
                    "incident": incident_dict(other),
                    "similarity_score": match.similarity_score,
                    "factors": match.factors,
                    "text_method": match.text_method,
                    "already_grouped": match.incident_id in grouped,
                }
            )
        clusters = [cluster_dict(session, c) for c in services["clusters_repo"].list_for_incident(incident_id)]
        return {"candidates": candidates, "clusters": clusters, "text_method": method}

    @router.post("/incidents/{incident_id}/duplicates/cluster", status_code=201)
    def create_cluster(
        incident_id: str,
        payload: ClusterRequest,
        principal: AuthPrincipal = Depends(allow(*SUPERVISOR)),
        session: Session = S,
    ):
        get_incident_for(session, incident_id, principal)
        service = svc(session)["duplicates"]
        scores = dict(service.find_candidates(incident_id))
        chosen = [(cid, scores[cid]) for cid in payload.candidate_ids if cid in scores]
        if not chosen:
            raise HTTPException(status_code=400, detail="None of those incidents are duplicate candidates")
        cluster = service.create_candidate_cluster(incident_id, chosen)
        session.commit()
        session.refresh(cluster)
        return cluster_dict(session, cluster)

    @router.post("/duplicate-clusters/{cluster_id}/confirm")
    def confirm_cluster(cluster_id: str, principal: AuthPrincipal = Depends(allow(*SUPERVISOR)), session: Session = S):
        try:
            cluster = svc(session)["duplicates"].confirm_cluster(cluster_id, principal.user_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail="Cluster not found") from error
        session.commit()
        return cluster_dict(session, cluster)

    @router.post("/duplicate-clusters/{cluster_id}/reject")
    def reject_cluster(cluster_id: str, principal: AuthPrincipal = Depends(allow(*SUPERVISOR)), session: Session = S):
        try:
            cluster = svc(session)["duplicates"].reject_cluster(cluster_id, principal.user_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail="Cluster not found") from error
        session.commit()
        return cluster_dict(session, cluster)

    # ----------------------------------------------------------- priority queue

    @router.get("/queue")
    def queue(
        status: IncidentStatus = IncidentStatus.READY_FOR_REVIEW,
        limit: int = 100,
        principal: AuthPrincipal = Depends(allow(*SUPERVISOR)),
        session: Session = S,
    ):
        items = svc(session)["priority"].build_queue(limit=min(limit, 300), status=status)
        return [
            {
                "incident": incident_dict(item["incident"]),
                "risk": risk_dict(item["risk"]),
                "work_orders": [order_dict(o) for o in item["work_orders"]],
            }
            for item in items
        ]

    # ----------------------------------------------------------- work orders

    @router.post("/incidents/{incident_id}/work-orders", status_code=201)
    def create_order(
        incident_id: str,
        payload: WorkOrderCreate,
        principal: AuthPrincipal = Depends(allow(*SUPERVISOR)),
        session: Session = S,
    ):
        get_incident_for(session, incident_id, principal)
        order = svc(session)["orders"].create_order(incident_id, payload.priority, payload.estimated_volume, principal.user_id)
        session.commit()
        return order_dict(order)

    @router.get("/incidents/{incident_id}/work-orders")
    def incident_orders(incident_id: str, principal: AuthPrincipal = Depends(allow(*STAFF)), session: Session = S):
        get_incident_for(session, incident_id, principal)
        orders = svc(session)["orders_repo"].list_for_incident(incident_id)
        who = names(session, {o.assigned_to for o in orders})
        return [order_dict(o, users=who) for o in orders]

    @router.get("/work-orders")
    def list_orders(
        status: WorkOrderStatus | None = None,
        limit: int = 200,
        principal: AuthPrincipal = Depends(allow(*STAFF)),
        session: Session = S,
    ):
        assigned_to = principal.user_id if principal.role == UserRole.SANITATION_WORKER else None
        orders = svc(session)["orders_repo"].list_filtered(status=status, assigned_to=assigned_to, limit=min(limit, 500))
        who = names(session, {o.assigned_to for o in orders})
        return [order_dict(o, session.get(Incident, o.incident_id), who) for o in orders]

    def own_order(session: Session, order_id: str, principal: AuthPrincipal) -> WorkOrder:
        order = session.get(WorkOrder, order_id)
        if order is None or (principal.role == UserRole.SANITATION_WORKER and order.assigned_to != principal.user_id):
            raise HTTPException(status_code=404, detail="Work order not found")
        return order

    @router.get("/work-orders/{order_id}")
    def get_order(order_id: str, principal: AuthPrincipal = Depends(allow(*STAFF)), session: Session = S):
        order = own_order(session, order_id, principal)
        who = names(session, {order.assigned_to})
        return order_dict(order, session.get(Incident, order.incident_id), who)

    @router.post("/work-orders/{order_id}/approve")
    def approve_order(order_id: str, principal: AuthPrincipal = Depends(allow(*SUPERVISOR)), session: Session = S):
        order = svc(session)["orders"].approve_order(order_id, principal.user_id)
        session.commit()
        return order_dict(order)

    @router.post("/work-orders/{order_id}/assign")
    def assign_order(order_id: str, payload: AssignRequest, principal: AuthPrincipal = Depends(allow(*SUPERVISOR)), session: Session = S):
        order = svc(session)["orders"].assign_order(order_id, payload.worker_id, principal.user_id)
        session.commit()
        return order_dict(order, users=names(session, {order.assigned_to}))

    @router.post("/work-orders/{order_id}/start")
    def start_order(order_id: str, principal: AuthPrincipal = Depends(allow(*WORKER)), session: Session = S):
        own_order(session, order_id, principal)
        order = svc(session)["orders"].start_order(order_id, principal.user_id)
        session.commit()
        return order_dict(order)

    @router.post("/work-orders/{order_id}/complete")
    def complete_order(order_id: str, principal: AuthPrincipal = Depends(allow(*WORKER)), session: Session = S):
        own_order(session, order_id, principal)
        order = svc(session)["orders"].complete_order(order_id, principal.user_id)
        session.commit()
        return order_dict(order)

    # ----------------------------------------------------------- routes

    def route_dict(session: Session, plan: RoutePlan) -> dict[str, Any]:
        stops = []
        for stop in svc(session)["routes_repo"].stops_for(plan.id):
            order = session.get(WorkOrder, stop.work_order_id)
            incident = session.get(Incident, order.incident_id) if order else None
            stops.append(
                {
                    "sequence": stop.sequence,
                    "work_order_id": stop.work_order_id,
                    "planned_volume": stop.planned_volume,
                    "priority": order.priority if order else None,
                    "incident": incident_dict(incident) if incident else None,
                }
            )
        saving = None
        if plan.baseline_distance_km and plan.estimated_distance_km is not None and plan.baseline_distance_km > 0:
            saving = (plan.baseline_distance_km - plan.estimated_distance_km) / plan.baseline_distance_km
        greedy = (plan.constraints or {}).get("greedy_distance_km")
        vs_greedy = None
        if greedy and plan.estimated_distance_km is not None and greedy > 0:
            vs_greedy = (greedy - plan.estimated_distance_km) / greedy
        return {
            "id": plan.id,
            "solver": (plan.constraints or {}).get("solver"),
            "greedy_distance_km": greedy,
            "greedy_order": (plan.constraints or {}).get("greedy_order"),
            "selection_order": (plan.constraints or {}).get("selection_order"),
            "depot": (plan.constraints or {}).get("depot"),
            "saving_vs_greedy": vs_greedy,
            "max_duration_minutes": (plan.constraints or {}).get("max_duration_minutes"),
            "vehicle_capacity": plan.vehicle_capacity,
            "estimated_distance_km": plan.estimated_distance_km,
            "estimated_duration_minutes": plan.estimated_duration_minutes,
            "baseline_distance_km": plan.baseline_distance_km,
            "saving_ratio": saving,
            "approved_by": plan.approved_by,
            "engine_version": (plan.constraints or {}).get("engine_version"),
            "created_at": _iso(plan.created_at),
            "stops": stops,
        }

    @router.get("/routes")
    def list_routes(principal: AuthPrincipal = Depends(allow(*SUPERVISOR)), session: Session = S):
        return [route_dict(session, p) for p in svc(session)["routes_repo"].list_all()]

    @router.post("/routes", status_code=201)
    def create_route(payload: RouteCreate, principal: AuthPrincipal = Depends(allow(*SUPERVISOR)), session: Session = S):
        depot = None
        if payload.depot_latitude is not None and payload.depot_longitude is not None:
            depot = (payload.depot_latitude, payload.depot_longitude)
        limits = {"max_duration_minutes": payload.max_duration_minutes} if payload.max_duration_minutes else {}
        plan = svc(session)["routes"].build_route(
            payload.work_order_ids, payload.vehicle_capacity, limits, principal.user_id, None, depot
        )
        session.commit()
        return route_dict(session, plan)

    @router.post("/routes/preview")
    def preview_route(payload: RouteCreate, principal: AuthPrincipal = Depends(allow(*SUPERVISOR)), session: Session = S):
        depot = None
        if payload.depot_latitude is not None and payload.depot_longitude is not None:
            depot = (payload.depot_latitude, payload.depot_longitude)
        limits = {"max_duration_minutes": payload.max_duration_minutes} if payload.max_duration_minutes else {}
        plan = svc(session)["routes"].preview_route(payload.work_order_ids, payload.vehicle_capacity, limits, principal.user_id, depot)
        result = plan["result"]
        saving = (plan["baseline_km"] - result.distance_km) / plan["baseline_km"] if plan["baseline_km"] > 0 else None
        vs_greedy = (result.greedy_distance_km - result.distance_km) / result.greedy_distance_km if result.greedy_distance_km > 0 else None
        return {
            "id": "preview",
            "solver": result.solver,
            "greedy_distance_km": result.greedy_distance_km,
            "saving_vs_greedy": vs_greedy,
            "greedy_order": result.greedy_order,
            "selection_order": plan["selection_order"],
            "depot": list(depot) if depot else None,
            "max_duration_minutes": payload.max_duration_minutes,
            "vehicle_capacity": payload.vehicle_capacity,
            "estimated_distance_km": result.distance_km,
            "estimated_duration_minutes": result.duration_minutes,
            "baseline_distance_km": plan["baseline_km"],
            "saving_ratio": saving,
            "approved_by": None,
            "engine_version": result.engine_version,
            "created_at": None,
            "total_volume": result.total_volume,
            "stops": [
                {
                    "sequence": stop.sequence,
                    "work_order_id": stop.work_order_id,
                    "planned_volume": stop.planned_volume,
                    "priority": plan["orders"][stop.work_order_id].priority,
                    "incident": incident_dict(plan["incidents"][str(plan["orders"][stop.work_order_id].incident_id)]),
                }
                for stop in result.stops
            ],
        }

    @router.get("/routes/{route_id}")
    def get_route(route_id: str, principal: AuthPrincipal = Depends(allow(*SUPERVISOR)), session: Session = S):
        plan = session.get(RoutePlan, route_id)
        if plan is None:
            raise HTTPException(status_code=404, detail="Route not found")
        return route_dict(session, plan)

    @router.post("/routes/{route_id}/approve")
    def approve_route(route_id: str, principal: AuthPrincipal = Depends(allow(*SUPERVISOR)), session: Session = S):
        try:
            plan = svc(session)["routes"].approve_route(route_id, principal.user_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail="Route not found") from error
        session.commit()
        return route_dict(session, plan)

    # ----------------------------------------------------------- verification & media

    @router.post("/incidents/{incident_id}/verification", status_code=201)
    async def submit_verification(
        incident_id: str,
        file: UploadFile = File(...),
        notes: str | None = Form(default=None),
        principal: AuthPrincipal = Depends(allow(*WORKER)),
        session: Session = S,
    ):
        if not file.content_type or not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="An image upload is required")
        content = await file.read(MAX_IMAGE_BYTES + 1)
        if len(content) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail="Image exceeds 10 MB limit")
        record = svc(session)["verification"].submit_evidence(
            incident_id, principal.user_id, content, notes, file.content_type
        )
        session.commit()
        return verification_dict(record)

    @router.get("/incidents/{incident_id}/verification")
    def latest_verification(incident_id: str, principal: AuthPrincipal = Depends(ctx.principal), session: Session = S):
        get_incident_for(session, incident_id, principal)
        return verification_dict(svc(session)["verification"].latest_verification(incident_id))

    @router.post("/verification/{record_id}/review")
    def review_verification(
        record_id: str,
        payload: ReviewRequest,
        principal: AuthPrincipal = Depends(allow(*SUPERVISOR)),
        session: Session = S,
    ):
        services = svc(session)
        record = services["verification"].review_evidence(record_id, principal.user_id, payload.status, payload.reason)
        if payload.status == VerificationStatus.REJECTED:
            for order in services["orders_repo"].list_for_incident(record.incident_id):
                if order.status == WorkOrderStatus.COMPLETED:
                    # review_evidence already set the incident back to in-progress; reopen the order to match.
                    order.status = WorkOrderStatus.IN_PROGRESS
        session.commit()
        return verification_dict(record)

    @router.get("/media/{asset_id}/content")
    def media_content(asset_id: str, principal: AuthPrincipal = Depends(ctx.principal), session: Session = S):
        asset = session.get(MediaAsset, asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="Photo not found")
        get_incident_for(session, asset.incident_id, principal)
        try:
            data = ctx.storage.get(asset.storage_key)
        except StorageObjectNotFound as error:
            raise HTTPException(status_code=404, detail="Photo file is missing from storage") from error
        return Response(content=data, media_type=asset.content_type, headers={"Cache-Control": "private, max-age=300"})

    # ----------------------------------------------------------- evaluation & pilots

    def is_pilot(run: Any) -> bool:
        return "start_date" in (run.metrics or {})

    @router.get("/evaluations")
    def list_evaluations(principal: AuthPrincipal = Depends(allow(*SUPERVISOR)), session: Session = S):
        return [run_dict(r) for r in svc(session)["evaluations_repo"].list_all() if not is_pilot(r)]

    @router.post("/evaluations/run", status_code=201)
    def run_evaluation(payload: EvaluationRequest, principal: AuthPrincipal = Depends(allow(*SUPERVISOR)), session: Session = S):
        def count(*where: Any) -> int:
            return session.scalar(select(func.count()).select_from(Incident).where(*where)) or 0

        total = count()

        def verified_closure() -> float:
            resolved = count(Incident.status.in_([IncidentStatus.RESOLVED, IncidentStatus.VERIFIED]))
            return round(count(Incident.status == IncidentStatus.VERIFIED) / resolved, 4) if resolved else 0.0

        def mean_confidence() -> float:
            value = session.scalar(select(func.avg(AnalysisResult.confidence)))
            return round(float(value), 4) if value is not None else 0.0

        def route_saving() -> float:
            plans = session.scalars(select(RoutePlan)).all()
            ratios = [
                (p.baseline_distance_km - p.estimated_distance_km) / p.baseline_distance_km
                for p in plans
                if p.baseline_distance_km and p.estimated_distance_km is not None
            ]
            return round(sum(ratios) / len(ratios), 4) if ratios else 0.0

        def supervisor_override_rate() -> float:
            overrides = session.scalar(
                select(func.count()).select_from(WorkOrder).where(WorkOrder.override_reason.is_not(None))
            ) or 0
            orders = session.scalar(select(func.count()).select_from(WorkOrder)) or 0
            return round(overrides / orders, 4) if orders else 0.0

        run = svc(session)["evaluation"].run_evaluation(
            payload.dataset_version,
            payload.name,
            {
                "incidents_total": lambda: total,
                "verified_closure_rate": verified_closure,
                "mean_ai_confidence": mean_confidence,
                "mean_route_saving": route_saving,
                "supervisor_override_rate": supervisor_override_rate,
            },
        )
        session.commit()
        return run_dict(run)

    @router.get("/evaluations/{run_id}/comparison")
    def evaluation_comparison(run_id: str, principal: AuthPrincipal = Depends(allow(*SUPERVISOR)), session: Session = S):
        return svc(session)["evaluation"].compare_with_baseline(run_id)

    @router.get("/pilots")
    def list_pilots(principal: AuthPrincipal = Depends(allow(*SUPERVISOR)), session: Session = S):
        return [run_dict(r) for r in svc(session)["evaluations_repo"].list_all() if is_pilot(r)]

    @router.post("/pilots", status_code=201)
    def start_pilot(payload: PilotCreate, principal: AuthPrincipal = Depends(allow(*SUPERVISOR)), session: Session = S):
        run = svc(session)["pilot"].start_pilot(
            payload.name, payload.location, payload.start_date, payload.end_date, payload.baseline_version, principal.user_id
        )
        session.commit()
        return run_dict(run)

    @router.post("/pilots/{pilot_id}/metrics")
    def pilot_metrics(pilot_id: str, payload: PilotMetrics, principal: AuthPrincipal = Depends(allow(*SUPERVISOR)), session: Session = S):
        run = svc(session)["pilot"].collect_metrics(pilot_id, dict(payload.metrics))
        session.commit()
        return run_dict(run)

    @router.post("/pilots/{pilot_id}/close")
    def close_pilot(pilot_id: str, principal: AuthPrincipal = Depends(allow(*SUPERVISOR)), session: Session = S):
        run = svc(session)["pilot"].close_pilot(pilot_id, principal.user_id)
        session.commit()
        return run_dict(run)

    # ----------------------------------------------------------- sensors

    @router.get("/sensors/readings")
    def recent_readings(limit: int = 50, principal: AuthPrincipal = Depends(allow(*SUPERVISOR)), session: Session = S):
        rows = session.scalars(select(SensorReading).order_by(SensorReading.observed_at.desc()).limit(min(limit, 200))).all()
        return [reading_dict(r) for r in rows]

    @router.post("/sensors/readings", status_code=201)
    def ingest_reading(payload: SensorReadingCreate, principal: AuthPrincipal = Depends(allow(*SUPERVISOR)), session: Session = S):
        reading = svc(session)["iot"].ingest_reading(
            payload.sensor_id,
            payload.latitude,
            payload.longitude,
            dict(payload.reading),
            payload.observed_at or datetime.now(timezone.utc),
        )
        session.commit()
        return reading_dict(reading)

    @router.get("/sensors/{sensor_id}/latest")
    def latest_reading(sensor_id: str, principal: AuthPrincipal = Depends(allow(*SUPERVISOR)), session: Session = S):
        reading = svc(session)["iot"].latest_reading(sensor_id)
        if reading is None:
            raise HTTPException(status_code=404, detail="No readings for that sensor")
        return reading_dict(reading)

    @router.post("/sensors/readings/{reading_id}/associate")
    def associate_reading(reading_id: str, payload: AssociateRequest, principal: AuthPrincipal = Depends(allow(*SUPERVISOR)), session: Session = S):
        reading = svc(session)["iot"].associate_with_incident(reading_id, payload.incident_id)
        session.commit()
        return reading_dict(reading)

    # ----------------------------------------------------------- supervisor dashboard

    @router.get("/dashboard/summary")
    def dashboard_summary(days: int = 14, principal: AuthPrincipal = Depends(allow(*SUPERVISOR)), session: Session = S):
        return svc(session)["dashboard"].summary(days=max(7, min(days, 60)))

    @router.get("/dashboard/map")
    def dashboard_map(principal: AuthPrincipal = Depends(allow(*SUPERVISOR)), session: Session = S):
        return svc(session)["dashboard"].map_points()

    # ----------------------------------------------------------- models

    @router.get("/ml/status")
    def ml_status(principal: AuthPrincipal = Depends(allow(*SUPERVISOR)), session: Session = S):
        return svc(session)["ml"].status()

    @router.post("/ml/risk/train")
    def train_risk(principal: AuthPrincipal = Depends(allow(UserRole.ADMIN)), session: Session = S):
        result = svc(session)["ml"].train_risk(principal.user_id)
        session.commit()
        return result

    # ----------------------------------------------------------- municipal

    @router.post("/municipal/export")
    def municipal_export(payload: MunicipalExport, principal: AuthPrincipal = Depends(allow(*SUPERVISOR)), session: Session = S):
        response = svc(session)["municipal"].export_work_orders(
            payload.work_order_ids, payload.system_name, principal.user_id, ManualMunicipalAdapter()
        )
        session.commit()
        return response

    @router.post("/municipal/import")
    def municipal_import(payload: MunicipalImport, principal: AuthPrincipal = Depends(allow(*SUPERVISOR)), session: Session = S):
        updates = [{"work_order_id": u.work_order_id, "status": u.status.value} for u in payload.updates]
        imported = svc(session)["municipal"].import_status_updates(
            updates, payload.system_name, principal.user_id, ManualMunicipalAdapter()
        )
        session.commit()
        return {"imported": imported, "received": len(updates)}

    return router
