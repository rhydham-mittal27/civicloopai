from datetime import datetime, timezone

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from civicloop.db import Base, init_db
from civicloop.models import Incident, IncidentStatus, ReporterType, User, UserRole
from civicloop.repositories import IncidentRepository, UserRepository


def test_init_db_creates_planned_tables() -> None:
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)

    tables = set(inspect(engine).get_table_names())

    assert {
        "users",
        "incidents",
        "media_assets",
        "analysis_results",
        "duplicate_clusters",
        "duplicate_cluster_members",
        "risk_assessments",
        "work_orders",
        "route_plans",
        "route_stops",
        "verification_records",
        "audit_events",
        "evaluation_runs",
    } <= tables


def test_repositories_persist_and_query_incidents() -> None:
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)

    with Session(engine) as session:
        user = User(name="Supervisor", email="supervisor@example.com", role=UserRole.SUPERVISOR)
        UserRepository(session).add(user)
        incident = Incident(
            reporter_id=user.id,
            reporter_type=ReporterType.RESIDENT,
            description="Waste beside the market",
            latitude=30.7333,
            longitude=76.7794,
            occurred_at=datetime.now(timezone.utc),
            status=IncidentStatus.READY_FOR_REVIEW,
        )
        IncidentRepository(session).add(incident)
        session.commit()

        assert UserRepository(session).get_by_email("supervisor@example.com").id == user.id
        results = IncidentRepository(session).list_by_status(IncidentStatus.READY_FOR_REVIEW)
        assert [result.id for result in results] == [incident.id]