from __future__ import annotations

import os
import secrets
from collections.abc import Generator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Callable

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from civicloop.ai import AIAdapterError, create_analysis_adapter_from_env
from civicloop.auth import (
    AuthenticationError,
    AuthenticationService,
    AuthPrincipal,
    TokenAuthenticator,
    hash_password,
)
from civicloop.container import build_services
from civicloop.embeddings import warm_up_in_background
from civicloop.db import create_engine, create_session_factory, init_db
from civicloop.jobs import InMemoryJobQueue, JobDispatcher, JobQueue, create_queue_from_env
from civicloop.models import Incident, IncidentStatus, ReporterType, User, UserRole
from civicloop.repositories import IncidentRepository, JobRepository, UserRepository
from civicloop.routes_fleet import build_fleet_router
from civicloop.routes_ops import Ctx, build_ops_router
from civicloop.services.analysis import AnalysisAdapter
from civicloop.services.common import NotFoundError, PermissionDeniedError, ServiceError
from civicloop.storage import ObjectStorageAdapter, StorageError, create_storage_from_env
from civicloop.synthetic import SYNTHETIC_LIKE
from civicloop.tenancy import bind_tenant, get_or_create_tenant, normalise_pincode, platform_admin_emails
from civicloop.models import Tenant
from civicloop.worker import WorkerThread, make_worker

STAFF_ROLES = {UserRole.SUPERVISOR, UserRole.ADMIN, UserRole.SANITATION_WORKER}

# What a supervisor may set by hand. Approval, progress and verification only happen through
# their own flows (work orders, workers, evidence review) so a status cannot be faked.
MANUAL_TRANSITIONS: dict[IncidentStatus, set[IncidentStatus]] = {
    IncidentStatus.READY_FOR_REVIEW: {IncidentStatus.REJECTED, IncidentStatus.UNCERTAIN},
    IncidentStatus.UNCERTAIN: {IncidentStatus.READY_FOR_REVIEW, IncidentStatus.REJECTED},
}


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=12)
    role: UserRole = UserRole.REPORTER
    city: str = Field(min_length=2, max_length=120)
    state: str | None = Field(default=None, max_length=100)
    pincode: str = Field(min_length=6, max_length=10)


class LoginRequest(BaseModel):
    email: str
    password: str


class IncidentCreateRequest(BaseModel):
    reporter_type: ReporterType
    description: str = Field(min_length=1)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    occurred_at: datetime
    pincode: str | None = Field(default=None, max_length=10)


class StatusRequest(BaseModel):
    status: IncidentStatus


class IncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    reporter_id: str | None
    reporter_type: ReporterType
    description: str
    latitude: float
    longitude: float
    pincode: str | None = None
    occurred_at: datetime
    status: IncidentStatus


class JobResponse(BaseModel):
    id: str
    job_type: str
    status: str
    result: dict[str, Any] | None = None
    attempt_count: int
    last_error_code: str | None = None
    last_error_message: str | None = None


def _incident_response(incident: Incident) -> IncidentResponse:
    return IncidentResponse.model_validate(incident)


def _job_response(job) -> JobResponse:
    return JobResponse(
        id=job.id,
        job_type=job.job_type,
        status=job.status.value,
        result=job.result,
        attempt_count=job.attempt_count,
        last_error_code=job.last_error_code,
        last_error_message=job.last_error_message,
    )


def create_app(
    database_url: str | None = None,
    auth_secret: str | None = None,
    storage: ObjectStorageAdapter | None = None,
    analysis_adapter_factory: Callable[[], AnalysisAdapter] | None = None,
    queue: JobQueue | None = None,
    run_worker: bool | None = None,
) -> FastAPI:
    database_url = database_url or os.getenv("CIVICLOOP_DATABASE_URL", "sqlite:///civicloop.db")
    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    storage = storage or create_storage_from_env()
    queue = queue or create_queue_from_env()
    if analysis_adapter_factory is None and os.getenv("CIVICLOOP_AI_PROVIDER"):
        analysis_adapter_factory = create_analysis_adapter_from_env
    secret = auth_secret or os.getenv("CIVICLOOP_AUTH_SECRET")
    if not secret:
        if os.getenv("CIVICLOOP_ENV", "development").lower() == "production":
            raise ValueError("CIVICLOOP_AUTH_SECRET must be configured in production with at least 32 characters")
        # Development: a fresh random secret per process, never a published constant.
        secret = secrets.token_urlsafe(48)
    # Sign-in lasts 12 hours by default (a working shift); CIVICLOOP_TOKEN_TTL_SECONDS changes it.
    authenticator = TokenAuthenticator(secret, ttl_seconds=int(os.getenv("CIVICLOOP_TOKEN_TTL_SECONDS", str(12 * 3600))))
    # An in-memory queue is private to this process, so the API runs the worker itself.
    run_worker = isinstance(queue, InMemoryJobQueue) if run_worker is None else run_worker
    dispatcher = JobDispatcher(session_factory, queue)
    worker_thread = WorkerThread(make_worker(session_factory, queue, storage, analysis_adapter_factory)) if run_worker else None

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        init_db(engine)
        warm_up_in_background()  # loads the embedding model off the request path (no-op when disabled)
        if worker_thread is not None:
            worker_thread.start()
        yield
        if worker_thread is not None:
            worker_thread.stop()

    app = FastAPI(title="CivicLoopAI API", version="1.1.0", lifespan=lifespan)
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.storage = storage
    app.state.authenticator = authenticator
    app.state.analysis_adapter_factory = analysis_adapter_factory
    app.state.dispatcher = dispatcher

    def get_session() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    def current_principal(request: Request, session: Session = Depends(get_session)) -> AuthPrincipal:
        try:
            token = authenticator.authenticate(request.headers.get("Authorization", ""))
        except AuthenticationError as error:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)) from error
        # The database is the authority on role and active state, not the token.
        user = session.get(User, token.user_id)
        if user is None or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account is not active")
        home = session.get(Tenant, user.tenant_id)
        if home is None or not home.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="This city's account has been disabled")
        is_platform = user.role == UserRole.ADMIN and user.email in platform_admin_emails()
        tenant_id = user.tenant_id
        wanted = request.headers.get("X-Tenant-Id")
        if wanted and wanted != tenant_id:
            # Only a platform admin may step into another city, and only an existing one.
            target = session.get(Tenant, wanted) if is_platform else None
            if target is None:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot act in another city")
            tenant_id = target.id
        # From here on every query in this request is limited to one city.
        bind_tenant(session, tenant_id)
        return AuthPrincipal(user.id, user.role, token.expires_at, tenant_id, is_platform)

    def visible_incident(session: Session, incident_id: str, principal: AuthPrincipal) -> Incident:
        incident = IncidentRepository(session).get(incident_id)
        if incident is None or (principal.role == UserRole.REPORTER and incident.reporter_id != principal.user_id):
            raise HTTPException(status_code=404, detail="Incident not found")
        return incident

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/tenants")
    def list_tenants(q: str = "", session: Session = Depends(get_session)) -> list[dict[str, str | None]]:
        """Suggest verified cities while someone types. Needs two letters and returns a handful of names,
        so the public list cannot be dumped or used to learn which cities exist."""
        needle = q.strip()
        if len(needle) < 2:
            return []
        rows = session.scalars(
            select(Tenant)
            .where(Tenant.is_active.is_(True), Tenant.verified.is_(True), Tenant.slug != "default", Tenant.name.ilike(f"{needle}%"))
            .order_by(Tenant.name)
            .limit(8)
        )
        return [{"name": t.name, "state": t.state} for t in rows]

    @app.post("/api/v1/auth/register", status_code=201)
    def register(payload: RegisterRequest, request: Request, session: Session = Depends(get_session)) -> dict[str, Any]:
        users = UserRepository(session)
        email = payload.email.strip().lower()
        if users.get_by_email(email) is not None:
            raise HTTPException(status_code=409, detail="Email is already registered")
        pincode = normalise_pincode(payload.pincode)

        caller_admin: User | None = None
        auth_header = request.headers.get("Authorization", "")
        if auth_header:
            try:
                caller = authenticator.authenticate(auth_header)
                found = session.get(User, caller.user_id)
                if found is not None and found.is_active and found.role == UserRole.ADMIN:
                    caller_admin = found
            except AuthenticationError:
                caller_admin = None

        assigned_role = UserRole.REPORTER
        if caller_admin is not None and payload.role != UserRole.REPORTER:
            # An administrator adds people to their own city, whatever city the form says.
            tenant = session.get(Tenant, caller_admin.tenant_id)
            assigned_role = payload.role
        else:
            tenant, created = get_or_create_tenant(session, payload.city, payload.state)
            if payload.role != UserRole.REPORTER:
                # The first person to register a city administers it; after that only its admins can promote.
                residents = session.scalar(
                    select(func.count()).select_from(User).where(User.tenant_id == tenant.id, User.email.not_like(SYNTHETIC_LIKE))
                ) or 0
                if not created and residents > 0:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Cannot register with elevated role without administrative privileges",
                    )
                assigned_role = payload.role

        user = users.add(
            User(
                name=payload.name.strip(),
                email=email,
                role=assigned_role,
                password_hash=hash_password(payload.password),
                tenant_id=tenant.id,
                pincode=pincode,
            )
        )
        session.commit()
        return {
            "user_id": user.id,
            "email": user.email,
            "role": user.role.value,
            "city": tenant.name,
            "state": tenant.state,
            "pincode": user.pincode,
            "city_verified": tenant.verified,
        }

    @app.post("/api/v1/auth/login")
    def login(payload: LoginRequest, session: Session = Depends(get_session)) -> dict[str, str]:
        try:
            token = AuthenticationService(UserRepository(session), authenticator).login(payload.email, payload.password)
        except AuthenticationError as error:
            raise HTTPException(status_code=401, detail="Invalid credentials") from error
        return {"access_token": token, "token_type": "bearer"}

    @app.post("/api/v1/incidents", response_model=IncidentResponse, status_code=201)
    def create_incident(
        payload: IncidentCreateRequest,
        principal: AuthPrincipal = Depends(current_principal),
        session: Session = Depends(get_session),
    ) -> IncidentResponse:
        incident = build_services(session, app.state.storage)["incidents"].create_incident(
            principal.user_id,
            payload.reporter_type,
            payload.description,
            payload.latitude,
            payload.longitude,
            payload.occurred_at,
            payload.pincode,
        )
        session.commit()
        return _incident_response(incident)

    @app.get("/api/v1/incidents", response_model=list[IncidentResponse])
    def list_incidents(
        status_filter: IncidentStatus | None = None,
        pincode: str | None = None,
        limit: int = 50,
        principal: AuthPrincipal = Depends(current_principal),
        session: Session = Depends(get_session),
    ) -> list[IncidentResponse]:
        reporter_id = principal.user_id if principal.role == UserRole.REPORTER else None
        # simulated training history is not part of the live queue
        simulated = session.scalar(select(User.id).where(User.email.like(SYNTHETIC_LIKE)))
        items = IncidentRepository(session).list_filtered(
            status=status_filter, reporter_id=reporter_id, exclude_reporter_id=simulated, pincode=normalise_pincode(pincode), limit=max(1, min(limit, 200))
        )
        return [_incident_response(item) for item in items]

    @app.get("/api/v1/incidents/{incident_id}", response_model=IncidentResponse)
    def get_incident(
        incident_id: str,
        principal: AuthPrincipal = Depends(current_principal),
        session: Session = Depends(get_session),
    ) -> IncidentResponse:
        return _incident_response(visible_incident(session, incident_id, principal))

    @app.patch("/api/v1/incidents/{incident_id}/status", response_model=IncidentResponse)
    def change_status(
        incident_id: str,
        payload: StatusRequest,
        principal: AuthPrincipal = Depends(current_principal),
        session: Session = Depends(get_session),
    ) -> IncidentResponse:
        if principal.role not in {UserRole.SUPERVISOR, UserRole.ADMIN}:
            raise HTTPException(status_code=403, detail="Supervisor role required")
        incident = visible_incident(session, incident_id, principal)
        if payload.status not in MANUAL_TRANSITIONS.get(incident.status, set()):
            raise HTTPException(
                status_code=409,
                detail=f"A {incident.status.value.replace('_', ' ')} incident cannot be set to {payload.status.value.replace('_', ' ')} by hand",
            )
        incident = build_services(session, app.state.storage)["incidents"].change_status(
            incident_id, payload.status, principal.user_id
        )
        session.commit()
        return _incident_response(incident)

    @app.post("/api/v1/incidents/{incident_id}/media", status_code=201)
    async def upload_media(
        incident_id: str,
        file: UploadFile = File(...),
        principal: AuthPrincipal = Depends(current_principal),
        session: Session = Depends(get_session),
    ) -> dict[str, Any]:
        visible_incident(session, incident_id, principal)
        if not file.content_type or not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="An image upload is required")
        chunks: list[bytes] = []
        total_size = 0
        max_size = 10 * 1024 * 1024
        while chunk := await file.read(1024 * 1024):
            total_size += len(chunk)
            if total_size > max_size:
                raise HTTPException(status_code=413, detail="Image exceeds 10 MB limit")
            chunks.append(chunk)
        content = b"".join(chunks)
        if not content:
            raise HTTPException(status_code=400, detail="Image cannot be empty")
        asset = build_services(session, app.state.storage)["media"].store_for_incident(
            incident_id, content, file.content_type
        )
        session.commit()
        return {
            "id": asset.id,
            "storage_key": asset.storage_key,
            "sha256": asset.sha256,
            "content_type": asset.content_type,
            "is_after_cleanup": asset.is_after_cleanup,
        }

    @app.get("/api/v1/incidents/{incident_id}/media")
    def list_media(
        incident_id: str,
        principal: AuthPrincipal = Depends(current_principal),
        session: Session = Depends(get_session),
    ) -> list[dict[str, Any]]:
        visible_incident(session, incident_id, principal)
        return [
            {
                "id": asset.id,
                "storage_key": asset.storage_key,
                "content_type": asset.content_type,
                "sha256": asset.sha256,
                "is_after_cleanup": asset.is_after_cleanup,
            }
            for asset in build_services(session, app.state.storage)["media"].list_evidence(incident_id)
        ]

    @app.post("/api/v1/incidents/{incident_id}/analysis")
    def analyze_incident(
        incident_id: str,
        async_mode: bool = False,
        principal: AuthPrincipal = Depends(current_principal),
        session: Session = Depends(get_session),
    ) -> dict[str, Any]:
        if principal.role not in STAFF_ROLES:
            raise HTTPException(status_code=403, detail="Analysis permission required")
        incident = visible_incident(session, incident_id, principal)
        if app.state.analysis_adapter_factory is None:
            raise HTTPException(status_code=503, detail="AI analysis is not configured on this server")
        if async_mode:
            stamp = (incident.updated_at or incident.created_at).isoformat()
            job = app.state.dispatcher.dispatch(
                job_type="analyze_incident",
                payload={"incident_id": incident_id},
                idempotency_key=f"analysis:{incident_id}:{stamp}",
                created_by=principal.user_id,
                priority="high",
                tenant_id=principal.tenant_id,
            )
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content={"job_id": job.id, "status": job.status.value, "detail": "Analysis job queued"},
            )
        services = build_services(session, app.state.storage)
        result = services["analysis"].analyze_incident(incident_id, app.state.analysis_adapter_factory())
        session.commit()
        # Score the hotspot right away so the supervisor queue is ranked without extra steps.
        risk = services["risk"].calculate_risk(incident_id)
        session.commit()
        return {
            "id": result.id,
            "incident_id": result.incident_id,
            "provider": result.provider,
            "model_name": result.model_name,
            "category": result.category,
            "severity": result.severity,
            "confidence": result.confidence,
            "risk_score": risk.score,
            "status": "ready_for_review",
        }

    @app.get("/api/v1/jobs/{job_id}", response_model=JobResponse)
    def get_job(
        job_id: str,
        principal: AuthPrincipal = Depends(current_principal),
        session: Session = Depends(get_session),
    ) -> JobResponse:
        job = JobRepository(session).get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if job.created_by not in {None, principal.user_id} and principal.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Job access denied")
        return _job_response(job)

    ops_ctx = Ctx(
        get_session=get_session,
        principal=current_principal,
        storage=storage,
        dispatcher=dispatcher,
        system={
            "ai_configured": analysis_adapter_factory is not None,
            "ai_provider": os.getenv("CIVICLOOP_AI_PROVIDER") if analysis_adapter_factory is not None else None,
            "worker": "in-process" if run_worker else "external",
            "storage": type(storage).__name__,
            "queue": type(queue).__name__,
        },
    )
    app.include_router(build_ops_router(ops_ctx))
    app.include_router(build_fleet_router(ops_ctx))

    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, error: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @app.exception_handler(PermissionDeniedError)
    async def denied_handler(request: Request, error: PermissionDeniedError) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(error)})

    @app.exception_handler(AIAdapterError)
    async def ai_handler(request: Request, error: AIAdapterError) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": str(error) or "The AI provider failed"})

    @app.exception_handler(StorageError)
    async def storage_handler(request: Request, error: StorageError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(error) or "Storage error"})

    @app.exception_handler(ServiceError)
    async def service_handler(request: Request, error: ServiceError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, error: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(error)})

    return app


app = create_app()
