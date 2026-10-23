"""Demo data: reports, approved work orders and planned routes, so every screen has something to show.

    python -m civicloop.demo                      # uses CIVICLOOP_DATABASE_URL
    python -m civicloop.demo --database-url sqlite:///civicloop.db

It writes through the real services (risk scoring, work orders, OR-Tools route planning), and
adds AI analyses labelled provider="demo", so no Gemini quota is needed. Run it once per database.
"""

from __future__ import annotations

import argparse
import os
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from civicloop.container import build_services
from civicloop.models import AnalysisResult, Incident, IncidentStatus, ReporterType, User, UserRole, VerificationRecord, VerificationStatus
from civicloop.storage import InMemoryObjectStorage

DEMO_RESIDENT = "demo-resident@civicloop.local"

# (description, latitude, longitude, severity, category)
SITES = [
    ("Overflowing bins behind the Sector 17 market", 30.7398, 76.7827, "high", "mixed_waste"),
    ("Construction rubble on the footpath near Sector 22 bus stop", 30.7333, 76.7715, "medium", "construction_debris"),
    ("Food waste piling up outside the Sector 35 eatery", 30.7214, 76.7568, "high", "organic_waste"),
    ("Plastic bags and bottles around the Rock Garden entrance", 30.7525, 76.8101, "medium", "plastic_waste"),
    ("Old sofa and mattress dumped by the Sector 8 school wall", 30.7551, 76.7948, "low", "bulk_waste"),
    ("Garbage heap at the Sector 15 petrol pump", 30.7442, 76.7711, "critical", "mixed_waste"),
    ("Dustbin overflowing at the Sector 34 temple", 30.7139, 76.7637, "medium", "mixed_waste"),
    ("Drain blocked and waste spilling onto the Sector 26 lane", 30.7268, 76.8005, "high", "mixed_waste"),
    ("Leaves and tree cuttings blocking the Sector 11 pavement", 30.7603, 76.7826, "low", "green_waste"),
    ("Burnt garbage near the Sector 43 bus terminal", 30.7160, 76.7456, "high", "mixed_waste"),
    ("Medical waste thrown outside the Sector 16 clinic", 30.7457, 76.7916, "critical", "medical_waste"),
    ("Litter and broken glass at the Sector 9 metro-style crossing", 30.7479, 76.7829, "medium", "mixed_waste"),
    ("Cardboard and packaging dumped behind the Sector 19 shops", 30.7311, 76.7838, "low", "mixed_waste"),
    ("Waste dumped in the vacant plot in Sector 44", 30.7098, 76.7551, "medium", "bulk_waste"),
    ("Smelly garbage near the Sector 7 fish market", 30.7502, 76.7742, "high", "organic_waste"),
    ("Bags of waste along the Sukhna choe", 30.7435, 76.8167, "medium", "plastic_waste"),
]

DEPOT = (30.7333, 76.7794)  # a central depot for the demo vehicles


def _user(session: Session, email: str, name: str, role: UserRole) -> User:
    user = session.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(name=name, email=email, role=role, pincode="160017")
        session.add(user)
        session.flush()
    return user


def _first(session: Session, role: UserRole, email: str, name: str) -> User:
    existing = session.scalar(select(User).where(User.role == role, User.is_active.is_(True)).order_by(User.created_at))
    return existing or _user(session, email, name, role)


def seed_demo(session: Session, seed: int = 11, city: str = "Chandigarh", pincode: str = "160017") -> dict[str, int]:
    """Returns counts of what was created. Everything lands in `city`."""
    from civicloop.tenancy import bind_tenant, get_or_create_tenant

    tenant, _ = get_or_create_tenant(session, city, verified=True)
    bind_tenant(session, tenant.id)
    if session.scalar(select(User).where(User.email == DEMO_RESIDENT)) is not None:
        raise SystemExit("Demo data is already in this database.")
    rng = random.Random(seed)
    services = build_services(session, InMemoryObjectStorage())
    resident = _user(session, DEMO_RESIDENT, "Demo Resident", UserRole.REPORTER)
    supervisor = _first(session, UserRole.SUPERVISOR, "demo-supervisor@civicloop.local", "Demo Supervisor")
    worker = _first(session, UserRole.SANITATION_WORKER, "demo-worker@civicloop.local", "Demo Worker")
    now = datetime.now(timezone.utc)

    order_ids: list[str] = []
    for i, (text, lat, lon, severity, category) in enumerate(SITES):
        age = rng.randint(2, 50)
        incident = services["incidents"].create_incident(
            resident.id, ReporterType.RESIDENT, text, lat, lon, now - timedelta(hours=age)
        )
        incident.created_at = now - timedelta(hours=age)
        incident.updated_at = incident.created_at
        session.add(
            AnalysisResult(
                incident_id=incident.id,
                provider="demo",
                model_name="demo-seed",
                category=category,
                severity=severity,
                confidence=round(rng.uniform(0.72, 0.96), 2),
                extracted_details={},
                raw_response={},
            )
        )
        incident.status = IncidentStatus.READY_FOR_REVIEW
        session.flush()
        services["risk"].calculate_risk(incident.id)
        priority = {"low": 20, "medium": 45, "high": 70, "critical": 90}[severity] + rng.randint(-5, 5)
        order = services["orders"].create_order(incident.id, priority, round(rng.uniform(1.0, 3.0), 1), supervisor.id)
        services["orders"].approve_order(order.id, supervisor.id)
        order_ids.append(order.id)

    first_run, second_run, spare = order_ids[:8], order_ids[8:13], order_ids[13:]
    plan_one = services["routes"].build_route(first_run, 20.0, {}, supervisor.id, None, DEPOT)
    services["routes"].approve_route(plan_one.id, supervisor.id)
    for order_id in first_run:
        services["orders"].assign_order(order_id, worker.id, supervisor.id)
    services["routes"].build_route(second_run, 14.0, {"max_duration_minutes": 240}, supervisor.id, None, DEPOT)
    # a few of the assigned jobs are already being worked
    for order_id in first_run[:3]:
        services["orders"].start_order(order_id, worker.id)
    extra = _extra_sightings(session, services, rng, resident, supervisor, worker, now)
    session.commit()
    return {"incidents": len(SITES) + extra, "routes": 2, "approved_routes": 1, "unrouted_orders": len(spare)}


_TEMPLATES = [
    ("mixed_waste", "Overflowing bins near {place}"),
    ("construction_debris", "Construction rubble dumped at {place}"),
    ("organic_waste", "Rotting waste piling up at {place}"),
    ("plastic_waste", "Plastic litter scattered around {place}"),
    ("bulk_waste", "Old furniture left outside {place}"),
]
_PLACES = ["the Sector {n} market", "the Sector {n} bus stop", "the Sector {n} park gate", "the Sector {n} school wall", "the Sector {n} petrol pump", "the Sector {n} community hall"]


def _extra_sightings(session: Session, services: dict, rng: random.Random, resident: User, supervisor: User, worker: User, now: datetime) -> int:
    """Sightings in every stage and age, so the dashboard and map are worth looking at."""

    def make(age_hours: float, status: IncidentStatus, severity: str | None, lat: float | None = None, lon: float | None = None, text: str | None = None, closed_after: float | None = None):
        lat = lat if lat is not None else rng.uniform(30.700, 30.768)
        lon = lon if lon is not None else rng.uniform(76.745, 76.815)
        category, template = rng.choice(_TEMPLATES)
        place = rng.choice(_PLACES).format(n=rng.choice([7, 9, 11, 15, 16, 17, 19, 22, 26, 27, 34, 35, 37, 43, 44]))
        created = now - timedelta(hours=age_hours)
        incident = Incident(
            reporter_id=resident.id,
            reporter_type=ReporterType.RESIDENT,
            description=text or template.format(place=place),
            latitude=lat,
            longitude=lon,
            occurred_at=created,
            status=status,
            created_at=created,
            updated_at=created + timedelta(hours=closed_after) if closed_after is not None else created,
        )
        session.add(incident)
        session.flush()
        if severity:
            session.add(AnalysisResult(incident_id=incident.id, provider="demo", model_name="demo-seed", category=category, severity=severity, confidence=round(rng.uniform(0.7, 0.96), 2), extracted_details={}, raw_response={}))
            session.flush()
            services["risk"].calculate_risk(incident.id)
        return incident

    made = 0
    for age in (0.5, 2, 6, 11, 19, 27):  # awaiting analysis
        make(age, IncidentStatus.PENDING_ANALYSIS, None)
        made += 1
    for age, severity in ((3, "medium"), (9, "high"), (18, "low"), (30, "high"), (44, "critical"), (55, "medium"), (70, "low")):  # waiting for review; some past their target
        make(age, IncidentStatus.READY_FOR_REVIEW, severity)
        made += 1
    for age, severity in ((10, "high"), (22, "medium"), (35, "critical"), (41, "low")):  # approved, nobody assigned yet
        incident = make(age, IncidentStatus.READY_FOR_REVIEW, severity)
        order = services["orders"].create_order(incident.id, {"low": 25, "medium": 50, "high": 75, "critical": 92}[severity], round(rng.uniform(1, 3), 1), supervisor.id)
        services["orders"].approve_order(order.id, supervisor.id)
        made += 1
    for age, severity in ((14, "high"), (26, "medium"), (33, "medium"), (47, "low")):  # crews on site
        incident = make(age, IncidentStatus.READY_FOR_REVIEW, severity)
        order = services["orders"].create_order(incident.id, 60, 2.0, supervisor.id)
        services["orders"].approve_order(order.id, supervisor.id)
        services["orders"].assign_order(order.id, worker.id, supervisor.id)
        services["orders"].start_order(order.id, worker.id)
        made += 1
    for age in (60, 90):  # cleaned, waiting for the evidence check
        incident = make(age, IncidentStatus.RESOLVED, "medium", closed_after=age * 0.6)
        made += 1
    for age in (52, 80):  # evidence needs a supervisor's decision
        incident = make(age, IncidentStatus.UNCERTAIN, "high")
        session.add(VerificationRecord(incident_id=incident.id, submitted_by=worker.id, status=VerificationStatus.UNCERTAIN, evidence_notes="After photo taken in low light"))
        made += 1
    # closed and verified over the last two weeks (drives the flow chart and closure time)
    for days_ago, took in ((0.4, 9), (1.2, 22), (1.8, 15), (2.5, 30), (3.3, 12), (4.4, 41), (6.1, 18), (7.5, 27), (9.2, 20), (11.0, 55), (12.5, 16)):
        make(days_ago * 24 + took, IncidentStatus.VERIFIED, rng.choice(["low", "medium", "medium", "high"]), closed_after=took)
        made += 1
    for age in (30, 75):
        make(age, IncidentStatus.REJECTED, "low", closed_after=2)
        made += 1
    # a recurring site: the same market keeps filling up
    for days_ago in (21, 38, 52, 66):
        make(days_ago * 24, IncidentStatus.VERIFIED, "high", lat=30.7398 + rng.uniform(-0.0012, 0.0012), lon=76.7827 + rng.uniform(-0.0012, 0.0012), text="Overflowing bins behind the Sector 17 market", closed_after=20)
        made += 1
    session.flush()
    return made


def main() -> None:
    from civicloop.db import create_engine, create_session_factory, init_db

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database-url", default=os.getenv("CIVICLOOP_DATABASE_URL", "sqlite:///civicloop.db"))
    parser.add_argument("--city", default="Chandigarh")
    parser.add_argument("--pincode", default="160017")
    args = parser.parse_args()
    engine = create_engine(args.database_url)
    init_db(engine)
    with create_session_factory(engine)() as session:
        print(seed_demo(session, city=args.city, pincode=args.pincode))


if __name__ == "__main__":
    main()
