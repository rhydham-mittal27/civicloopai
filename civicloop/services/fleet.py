"""Live vehicle tracking: vehicles, GPS fixes from a crew phone or a tracker, and what the map shows.

A fix is accepted only if it is plausible. A point that implies a speed no refuse truck can reach (a GPS
glitch or a bad clock) is dropped, so one bad reading cannot throw a vehicle across the city.
"""

from __future__ import annotations

import hashlib
import math
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from civicloop.models import User, UserRole, Vehicle, VehiclePing
from civicloop.repositories import AuditEventRepository
from civicloop.services.common import NotFoundError, ServiceError, record_audit

EARTH_RADIUS_KM = 6371.0088
MAX_SPEED_KMH = 160.0  # anything faster between two fixes is treated as a glitch
MAX_FUTURE = timedelta(minutes=5)  # tolerated clock drift on a phone or tracker
MAX_AGE = timedelta(hours=24)  # a late batch from a tracker that was out of signal
MIN_STORE_GAP = timedelta(seconds=4)  # history keeps at most one fix every few seconds
KEEP_HISTORY = timedelta(days=7)
MOVING_KMH = 3.0
FRESH = timedelta(minutes=2)  # a fix this young is "live"
STALE = timedelta(minutes=10)  # older than this the vehicle is offline
LOCAL_DAY = timezone(timedelta(hours=5, minutes=30))  # distance today is counted in Indian time
KEY_PREFIX = "clv_"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dlmb = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def new_device_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(24)


def vehicle_state(vehicle: Vehicle, now: datetime) -> str:
    """no_signal, moving, idle, stale or offline."""
    if vehicle.last_seen_at is None:
        return "no_signal"
    age = now - as_utc(vehicle.last_seen_at)
    if age > STALE:
        return "offline"
    if age > FRESH:
        return "stale"
    return "moving" if (vehicle.last_speed_kmh or 0) >= MOVING_KMH else "idle"


@dataclass
class Fix:
    lat: float
    lon: float
    recorded_at: datetime | None = None
    speed_kmh: float | None = None
    heading: float | None = None
    accuracy_m: float | None = None


class FleetService:
    def __init__(self, session: Session, audit: AuditEventRepository) -> None:
        self.session = session
        self.audit = audit

    # ------------------------------------------------------------------ vehicles

    def _check_driver(self, driver_id: str | None) -> None:
        if driver_id is None:
            return
        driver = self.session.get(User, driver_id)
        if driver is None or not driver.is_active or driver.role != UserRole.SANITATION_WORKER:
            raise ServiceError("A driver must be an active sanitation worker in this city")

    def create_vehicle(self, actor_id: str, label: str, registration: str | None, driver_id: str | None) -> tuple[Vehicle, str]:
        label = label.strip()
        if not label:
            raise ValueError("A vehicle needs a name")
        self._check_driver(driver_id)
        key = new_device_key()
        vehicle = Vehicle(
            label=label,
            registration=(registration or "").strip().upper() or None,
            driver_id=driver_id,
            device_key_hash=hash_key(key),
        )
        self.session.add(vehicle)
        self.session.flush()
        record_audit(self.audit, actor_id, "vehicle", vehicle.id, "created", {"label": label, "driver_id": driver_id})
        return vehicle, key

    def rotate_key(self, actor_id: str, vehicle_id: str) -> tuple[Vehicle, str]:
        vehicle = self.get(vehicle_id)
        key = new_device_key()
        vehicle.device_key_hash = hash_key(key)
        self.session.flush()
        record_audit(self.audit, actor_id, "vehicle", vehicle.id, "key_rotated", {})
        return vehicle, key

    def update_vehicle(self, actor_id: str, vehicle_id: str, changes: dict[str, Any]) -> Vehicle:
        vehicle = self.get(vehicle_id)
        applied: dict[str, Any] = {}
        if "label" in changes and changes["label"] is not None and changes["label"].strip():
            vehicle.label = changes["label"].strip()
            applied["label"] = vehicle.label
        if "registration" in changes and changes["registration"] is not None:
            vehicle.registration = changes["registration"].strip().upper() or None
            applied["registration"] = vehicle.registration
        if "driver_id" in changes:
            driver_id = changes["driver_id"] or None
            self._check_driver(driver_id)
            vehicle.driver_id = driver_id
            applied["driver_id"] = driver_id
        if changes.get("is_active") is not None:
            vehicle.is_active = bool(changes["is_active"])
            applied["is_active"] = vehicle.is_active
        self.session.flush()
        if applied:
            record_audit(self.audit, actor_id, "vehicle", vehicle.id, "updated", applied)
        return vehicle

    def get(self, vehicle_id: str) -> Vehicle:
        vehicle = self.session.get(Vehicle, vehicle_id)
        if vehicle is None:
            raise NotFoundError("Vehicle not found")
        return vehicle

    def list_vehicles(self) -> list[Vehicle]:
        return list(self.session.scalars(select(Vehicle).order_by(Vehicle.label)))

    def for_driver(self, driver_id: str) -> list[Vehicle]:
        rows = self.session.scalars(select(Vehicle).where(Vehicle.driver_id == driver_id, Vehicle.is_active.is_(True)).order_by(Vehicle.label))
        return list(rows)

    # ------------------------------------------------------------------ fixes

    def record(self, vehicle: Vehicle, fixes: Iterable[Fix], source: str, now: datetime | None = None) -> dict[str, int]:
        """Store the plausible fixes and move the vehicle. Returns how many were kept and dropped."""
        now = now or datetime.now(timezone.utc)
        kept = dropped = 0
        ordered = sorted(fixes, key=lambda f: as_utc(f.recorded_at) if f.recorded_at else now)
        prev_time = as_utc(vehicle.last_seen_at) if vehicle.last_seen_at else None
        prev_pos = (vehicle.last_lat, vehicle.last_lon) if vehicle.last_lat is not None else None
        stored_time = self._last_stored(vehicle.id)

        for fix in ordered:
            when = as_utc(fix.recorded_at) if fix.recorded_at else now
            if (
                not (-90 <= fix.lat <= 90 and -180 <= fix.lon <= 180)
                or when > now + MAX_FUTURE
                or when < now - MAX_AGE
                or (fix.accuracy_m is not None and fix.accuracy_m > 500)  # too vague to place a truck
            ):
                dropped += 1
                continue
            speed = fix.speed_kmh
            step_km = 0.0
            if prev_time is not None and prev_pos is not None and when > prev_time:
                seconds = (when - prev_time).total_seconds()
                step_km = haversine_km(prev_pos[0], prev_pos[1], fix.lat, fix.lon)
                implied = step_km / seconds * 3600 if seconds >= 1 else 0.0
                if implied > MAX_SPEED_KMH and seconds < 600:
                    dropped += 1  # a jump no truck can make: a glitch, not movement
                    continue
                if speed is None and 1 <= seconds <= 600:
                    speed = implied
                if seconds > 600:
                    step_km = 0.0  # a gap in the signal is not distance driven
            if speed is not None and not (0 <= speed <= MAX_SPEED_KMH):
                speed = None
            newest = prev_time is None or when > prev_time
            if stored_time is None or when - stored_time >= MIN_STORE_GAP or when < stored_time:
                self.session.add(
                    VehiclePing(
                        vehicle_id=vehicle.id,
                        lat=fix.lat,
                        lon=fix.lon,
                        speed_kmh=speed,
                        heading=fix.heading,
                        accuracy_m=fix.accuracy_m,
                        recorded_at=when,
                        source=source,
                    )
                )
                stored_time = when if stored_time is None or when > stored_time else stored_time
            if newest:
                self._count_distance(vehicle, when, step_km)
                vehicle.last_lat, vehicle.last_lon = fix.lat, fix.lon
                vehicle.last_speed_kmh = speed
                vehicle.last_heading = fix.heading
                vehicle.last_accuracy_m = fix.accuracy_m
                vehicle.last_seen_at = when
                vehicle.last_source = source
                prev_time, prev_pos = when, (fix.lat, fix.lon)
            kept += 1

        if kept:
            self.session.execute(delete(VehiclePing).where(VehiclePing.vehicle_id == vehicle.id, VehiclePing.recorded_at < now - KEEP_HISTORY))
        self.session.flush()
        return {"accepted": kept, "dropped": dropped}

    def _last_stored(self, vehicle_id: str) -> datetime | None:
        value = self.session.scalar(select(VehiclePing.recorded_at).where(VehiclePing.vehicle_id == vehicle_id).order_by(VehiclePing.recorded_at.desc()).limit(1))
        return as_utc(value) if value else None

    @staticmethod
    def _count_distance(vehicle: Vehicle, when: datetime, step_km: float) -> None:
        day = when.astimezone(LOCAL_DAY).strftime("%Y-%m-%d")
        if vehicle.day_key != day:
            vehicle.day_key, vehicle.day_distance_km = day, 0.0
        vehicle.day_distance_km = (vehicle.day_distance_km or 0.0) + step_km

    def distance_today_km(self, vehicle: Vehicle, now: datetime) -> float:
        today = now.astimezone(LOCAL_DAY).strftime("%Y-%m-%d")
        return round(vehicle.day_distance_km or 0.0, 1) if vehicle.day_key == today else 0.0

    def trail(self, vehicle_id: str, minutes: int, limit: int = 600, now: datetime | None = None) -> list[VehiclePing]:
        self.get(vehicle_id)
        since = (now or datetime.now(timezone.utc)) - timedelta(minutes=max(1, min(minutes, 24 * 60)))
        rows = self.session.scalars(
            select(VehiclePing).where(VehiclePing.vehicle_id == vehicle_id, VehiclePing.recorded_at >= since).order_by(VehiclePing.recorded_at.desc()).limit(limit)
        )
        return list(reversed(list(rows)))
