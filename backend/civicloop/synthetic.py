"""Synthetic report history, for demonstrating and testing the risk-model pipeline only.

Real deployments have no history on day one, so there is nothing to train on. This simulates a
city where waste recurs at hotspots in bursts, writes it to the database under a dedicated
"Synthetic history" account, and lets the training code run end to end. Anything trained on it
proves the plumbing, not real-world accuracy, and the models page flags the synthetic share.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from civicloop.models import AnalysisResult, Incident, IncidentStatus, ReporterType, Tenant, User, UserRole

SYNTHETIC_EMAIL = "synthetic-history@civicloop.local"
# every city has its own simulated-history account: synthetic-history+<city>@civicloop.local
SYNTHETIC_LIKE = "synthetic-history%@civicloop.local"


def synthetic_email(tenant_slug: str | None) -> str:
    return SYNTHETIC_EMAIL if not tenant_slug or tenant_slug == "default" else f"synthetic-history+{tenant_slug}@civicloop.local"

_TEMPLATES = [
    ("mixed_waste", "Overflowing bins and loose debris near {place}"),
    ("construction_debris", "Construction rubble dumped on the footpath at {place}"),
    ("organic_waste", "Rotting food waste piling up behind {place}"),
    ("plastic_waste", "Plastic bags and bottles scattered around {place}"),
    ("bulk_waste", "Old furniture and a mattress left outside {place}"),
]
_PLACES = ["the market", "the bus stop", "the park gate", "the school wall", "the petrol pump", "the temple road", "the metro exit"]


def seed_synthetic_history(
    session: Session,
    count: int = 1500,
    days: int = 365,
    seed: int = 7,
    now: datetime | None = None,
    hotspots: int = 120,
    hotspot_share: float = 0.4,
) -> int:
    """Insert `count` simulated reports spread over the last `days`. Returns how many were added."""
    rng = random.Random(seed)
    now = now or datetime.now(timezone.utc)
    user = session.scalar(select(User).where(User.email.like(SYNTHETIC_LIKE)))
    if user is None:
        from civicloop.tenancy import default_tenant, session_tenant

        tenant_id = session_tenant(session) or default_tenant(session).id
        slug = session.scalar(select(Tenant.slug).where(Tenant.id == tenant_id))
        user = User(name="Synthetic history", email=synthetic_email(slug), role=UserRole.REPORTER, is_active=False, tenant_id=tenant_id)
        session.add(user)
        session.flush()

    # A city box roughly 11 km x 12 km. Each hotspot has a heavy-tailed propensity and a severity.
    centres = [(rng.uniform(30.68, 30.78), rng.uniform(76.70, 76.82)) for _ in range(hotspots)]
    propensity = [rng.gammavariate(0.6, 1.0) + 0.05 for _ in range(hotspots)]
    base_severity = [rng.choice([0, 0, 1, 1, 2, 3]) for _ in range(hotspots)]
    bursts = [[rng.uniform(0, days) for _ in range(rng.randint(2, 6))] for _ in range(hotspots)]
    labels = ["low", "medium", "high", "critical"]
    jitter = 0.00115  # about 120 m

    added = 0
    for _ in range(count):
        if rng.random() < hotspot_share:
            h = rng.choices(range(hotspots), weights=propensity)[0]
            lat = centres[h][0] + rng.gauss(0, jitter)
            lon = centres[h][1] + rng.gauss(0, jitter)
            if rng.random() < 0.7:  # reports arrive in bursts that fade out
                age = max(0.0, days - (rng.choice(bursts[h]) + rng.expovariate(1 / 15)))
            else:
                age = rng.uniform(0, days)
            severity = labels[max(0, min(3, base_severity[h] + rng.choice([-1, 0, 0, 1])))]
        else:
            lat, lon = rng.uniform(30.68, 30.78), rng.uniform(76.70, 76.82)
            age = rng.uniform(0, days)
            severity = rng.choice(labels[:3])
        occurred = now - timedelta(days=age, minutes=rng.randint(0, 1439))
        category, template = rng.choice(_TEMPLATES)
        # History is closed work: it must not show up in today's queues.
        status = rng.choices(
            [IncidentStatus.VERIFIED, IncidentStatus.RESOLVED, IncidentStatus.REJECTED],
            weights=[65, 25, 10],
        )[0]
        incident = Incident(
            reporter_id=user.id,
            reporter_type=ReporterType.RESIDENT,
            description=template.format(place=rng.choice(_PLACES)),
            latitude=lat,
            longitude=lon,
            occurred_at=occurred,
            status=status,
        )
        session.add(incident)
        session.flush()
        session.add(
            AnalysisResult(
                incident_id=incident.id,
                provider="synthetic",
                model_name="synthetic",
                category=category,
                severity=severity,
                confidence=round(rng.uniform(0.6, 0.95), 2),
                extracted_details={},
                raw_response={},
            )
        )
        added += 1
    session.commit()
    return added
