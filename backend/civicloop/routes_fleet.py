"""Live fleet routes: manage vehicles, read where they are, and receive GPS from a phone or a tracker."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from civicloop.auth import AuthPrincipal
from civicloop.container import build_services
from civicloop.models import Tenant, User, UserRole, Vehicle
from civicloop.routes_ops import Ctx, SUPERVISOR, _iso
from civicloop.services.fleet import Fix, FleetService, as_utc, hash_key, vehicle_state
from civicloop.tenancy import bind_tenant

# a tracker sends a fix every few seconds, so this is generous but stops a loop or a leaked key
DEVICE_LIMIT = 240  # requests ...
DEVICE_WINDOW = 60.0  # ... per minute, per vehicle
_device_hits: dict[str, deque[float]] = defaultdict(deque)


def _device_allowed(vehicle_id: str) -> bool:
    now, hits = time.monotonic(), _device_hits[vehicle_id]
    while hits and now - hits[0] > DEVICE_WINDOW:
        hits.popleft()
    if len(hits) >= DEVICE_LIMIT:
        return False
    hits.append(now)
    return True


class VehicleCreate(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    registration: str | None = Field(default=None, max_length=40)
    driver_id: str | None = None


class VehiclePatch(BaseModel):
    label: str | None = Field(default=None, max_length=80)
    registration: str | None = Field(default=None, max_length=40)
    driver_id: str | None = None
    is_active: bool | None = None


class FixIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    speed_kmh: float | None = Field(default=None, ge=0, le=400)
    heading: float | None = Field(default=None, ge=0, le=360)
    accuracy_m: float | None = Field(default=None, ge=0)
    recorded_at: datetime | None = None

    def to_fix(self) -> Fix:
        return Fix(self.lat, self.lon, self.recorded_at, self.speed_kmh, self.heading, self.accuracy_m)


class DeviceReport(BaseModel):
    """Either one fix (lat, lon, ...) or a batch in `points`, for a tracker that buffered while out of signal."""

    points: list[FixIn] = Field(default_factory=list, max_length=200)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    speed_kmh: float | None = Field(default=None, ge=0, le=400)
    heading: float | None = Field(default=None, ge=0, le=360)
    accuracy_m: float | None = Field(default=None, ge=0)
    recorded_at: datetime | None = None

    @model_validator(mode="after")
    def need_a_fix(self) -> "DeviceReport":
        if not self.points and (self.lat is None or self.lon is None):
            raise ValueError("Send a fix (lat and lon) or a list of points")
        return self

    def fixes(self) -> list[Fix]:
        out = [p.to_fix() for p in self.points]
        if self.lat is not None and self.lon is not None:
            out.append(Fix(self.lat, self.lon, self.recorded_at, self.speed_kmh, self.heading, self.accuracy_m))
        return out


def vehicle_dict(session: Session, fleet: FleetService, v: Vehicle, now: datetime, names: dict[str, str]) -> dict[str, Any]:
    seen = as_utc(v.last_seen_at) if v.last_seen_at else None
    return {
        "id": v.id,
        "label": v.label,
        "registration": v.registration,
        "driver_id": v.driver_id,
        "driver_name": names.get(v.driver_id or ""),
        "is_active": v.is_active,
        "state": vehicle_state(v, now) if v.is_active else "disabled",
        "lat": v.last_lat,
        "lon": v.last_lon,
        "speed_kmh": round(v.last_speed_kmh, 1) if v.last_speed_kmh is not None else None,
        "heading": v.last_heading,
        "accuracy_m": v.last_accuracy_m,
        "last_seen_at": _iso(seen),
        "age_seconds": int((now - seen).total_seconds()) if seen else None,
        "source": v.last_source,
        "distance_today_km": fleet.distance_today_km(v, now),
    }


def build_fleet_router(ctx: Ctx) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    S = Depends(ctx.get_session)

    def allow(*roles: UserRole):
        allowed = set(roles)

        def dependency(principal: AuthPrincipal = Depends(ctx.principal)) -> AuthPrincipal:
            if principal.role not in allowed:
                raise HTTPException(status_code=403, detail="Your role cannot do this")
            return principal

        return dependency

    def fleet_for(session: Session) -> FleetService:
        return build_services(session, ctx.storage)["fleet"]

    def driver_names(session: Session, vehicles: list[Vehicle]) -> dict[str, str]:
        ids = {v.driver_id for v in vehicles if v.driver_id}
        if not ids:
            return {}
        return {row[0]: row[1] for row in session.execute(select(User.id, User.name).where(User.id.in_(ids))).all()}

    def present(session: Session, vehicles: list[Vehicle]) -> list[dict[str, Any]]:
        fleet, now = fleet_for(session), datetime.now(timezone.utc)
        names = driver_names(session, vehicles)
        return [vehicle_dict(session, fleet, v, now, names) for v in vehicles]

    # ------------------------------------------------------------ supervisors

    @router.get("/vehicles")
    def list_vehicles(principal: AuthPrincipal = Depends(allow(*SUPERVISOR)), session: Session = S):
        return present(session, fleet_for(session).list_vehicles())

    @router.post("/vehicles", status_code=201)
    def create_vehicle(payload: VehicleCreate, principal: AuthPrincipal = Depends(allow(*SUPERVISOR)), session: Session = S):
        vehicle, key = fleet_for(session).create_vehicle(principal.user_id, payload.label, payload.registration, payload.driver_id)
        session.commit()
        return {**present(session, [vehicle])[0], "device_key": key}

    @router.patch("/vehicles/{vehicle_id}")
    def patch_vehicle(vehicle_id: str, payload: VehiclePatch, principal: AuthPrincipal = Depends(allow(*SUPERVISOR)), session: Session = S):
        vehicle = fleet_for(session).update_vehicle(principal.user_id, vehicle_id, payload.model_dump(exclude_unset=True))
        session.commit()
        return present(session, [vehicle])[0]

    @router.post("/vehicles/{vehicle_id}/device-key")
    def rotate_key(vehicle_id: str, principal: AuthPrincipal = Depends(allow(*SUPERVISOR)), session: Session = S):
        """Issue a new tracker key. The old one stops working at once. The key is shown only here."""
        vehicle, key = fleet_for(session).rotate_key(principal.user_id, vehicle_id)
        session.commit()
        return {**present(session, [vehicle])[0], "device_key": key}

    @router.get("/vehicles/{vehicle_id}/trail")
    def trail(vehicle_id: str, minutes: int = 60, principal: AuthPrincipal = Depends(allow(*SUPERVISOR)), session: Session = S):
        pings = fleet_for(session).trail(vehicle_id, minutes)
        return [
            {"lat": p.lat, "lon": p.lon, "speed_kmh": p.speed_kmh, "heading": p.heading, "recorded_at": _iso(as_utc(p.recorded_at))}
            for p in pings
        ]

    # ------------------------------------------------------------ crews

    @router.get("/vehicles/mine")
    def my_vehicles(principal: AuthPrincipal = Depends(allow(UserRole.SANITATION_WORKER)), session: Session = S):
        return present(session, fleet_for(session).for_driver(principal.user_id))

    @router.post("/vehicles/{vehicle_id}/position")
    def share_position(
        vehicle_id: str,
        payload: FixIn,
        principal: AuthPrincipal = Depends(allow(UserRole.SANITATION_WORKER, *SUPERVISOR)),
        session: Session = S,
    ):
        """The crew's phone reports where the vehicle is. Only its assigned driver (or a supervisor) may."""
        fleet = fleet_for(session)
        vehicle = fleet.get(vehicle_id)
        if principal.role == UserRole.SANITATION_WORKER and vehicle.driver_id != principal.user_id:
            raise HTTPException(status_code=403, detail="This vehicle is not assigned to you")
        if not vehicle.is_active:
            raise HTTPException(status_code=409, detail="This vehicle is switched off")
        result = fleet.record(vehicle, [payload.to_fix()], "phone")
        session.commit()
        return result

    # ------------------------------------------------------------ trackers

    def device_vehicle(x_device_key: str = Header(default=""), session: Session = S) -> Vehicle:
        """A GPS tracker has no user login; it proves itself with the key issued for its vehicle."""
        if not x_device_key:
            raise HTTPException(status_code=401, detail="X-Device-Key header is required")
        vehicle = session.scalar(select(Vehicle).where(Vehicle.device_key_hash == hash_key(x_device_key)))
        if vehicle is None or not vehicle.is_active:
            raise HTTPException(status_code=401, detail="Unknown or switched-off device key")
        city = session.get(Tenant, vehicle.tenant_id)
        if city is None or not city.is_active:
            raise HTTPException(status_code=403, detail="This city is disabled")
        if not _device_allowed(vehicle.id):
            raise HTTPException(status_code=429, detail="Too many reports from this device. Send fewer, batched in `points`.", headers={"Retry-After": "30"})
        bind_tenant(session, vehicle.tenant_id)  # the tracker can only ever write into its own city
        return vehicle

    @router.post("/telemetry/gps")
    def device_gps(payload: DeviceReport, vehicle: Vehicle = Depends(device_vehicle), session: Session = S):
        result = fleet_for(session).record(vehicle, payload.fixes(), "device")
        session.commit()
        return result

    return router
