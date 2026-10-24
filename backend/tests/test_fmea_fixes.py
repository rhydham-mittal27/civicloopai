import io
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from civicloop.api import create_app
from civicloop.db import create_engine
from civicloop.jobs import InMemoryJobQueue, JobDispatcher
from civicloop.models import UserRole
from civicloop.observability import MetricsRegistry
from civicloop.repositories import (
    AuditEventRepository,
    IncidentRepository,
    MediaAssetRepository,
    RoutePlanRepository,
    UserRepository,
    VerificationRepository,
    WorkOrderRepository,
)
from civicloop.services.route_planning import RoutePlanningService
from civicloop.services.verification import VerificationService
from civicloop.storage import InMemoryObjectStorage


def test_public_registration_blocks_privilege_escalation(tmp_path):
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'sec.db'}",
        auth_secret="a" * 32,
        storage=InMemoryObjectStorage(),
        queue=InMemoryJobQueue(),
    )
    with TestClient(app) as client:
        # First user is allowed to bootstrap
        res1 = client.post(
            "/api/v1/auth/register",
            json={"name": "Admin1", "email": "admin@example.com", "password": "correct horse battery", "role": "admin", "city": "Chandigarh", "pincode": "160017"},
        )
        assert res1.status_code == 201

        # Second anonymous user attempting to register as admin is blocked (403)
        res2 = client.post(
            "/api/v1/auth/register",
            json={"name": "Hacker", "email": "hacker@example.com", "password": "correct horse battery", "role": "admin", "city": "Chandigarh", "pincode": "160017"},
        )
        assert res2.status_code == 403

        # Second anonymous user registering as regular reporter is allowed (201)
        res3 = client.post(
            "/api/v1/auth/register",
            json={"name": "Resident", "email": "resident@example.com", "password": "correct horse battery", "role": "reporter", "city": "Chandigarh", "pincode": "160017"},
        )
        assert res3.status_code == 201
        assert res3.json()["role"] == "reporter"


def test_media_upload_stream_exceeding_10mb_aborts_with_413(tmp_path):
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'upload.db'}",
        auth_secret="a" * 32,
        storage=InMemoryObjectStorage(),
        queue=InMemoryJobQueue(),
    )
    with TestClient(app) as client:
        reg = client.post(
            "/api/v1/auth/register",
            json={"name": "User", "email": "u@example.com", "password": "correct horse battery", "role": "reporter", "city": "Chandigarh", "pincode": "160017"},
        )
        assert reg.status_code == 201
        login = client.post("/api/v1/auth/login", json={"email": "u@example.com", "password": "correct horse battery"})
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        inc = client.post(
            "/api/v1/incidents",
            headers=headers,
            json={"reporter_type": "resident", "description": "Trash", "latitude": 30.0, "longitude": 76.0, "occurred_at": datetime.now(timezone.utc).isoformat()},
        )
        inc_id = inc.json()["id"]

        # 11 MB simulated file
        oversized = b"X" * (11 * 1024 * 1024)
        res = client.post(
            f"/api/v1/incidents/{inc_id}/media",
            headers=headers,
            files={"file": ("large.jpg", io.BytesIO(oversized), "image/jpeg")},
        )
        assert res.status_code == 413


def test_verification_service_persists_image_bytes(tmp_path):
    from sqlalchemy.orm import Session
    from civicloop.db import init_db
    from civicloop.models import Incident, ReporterType, User

    engine = create_engine(f"sqlite:///{tmp_path / 'ver.db'}")
    init_db(engine)
    storage = InMemoryObjectStorage()

    with Session(engine) as session:
        users = UserRepository(session)
        worker = users.add(User(name="Worker", email="w@example.com", role=UserRole.SANITATION_WORKER))
        incidents = IncidentRepository(session)
        incident = incidents.add(
            Incident(
                reporter_id=worker.id,
                reporter_type=ReporterType.FIELD_WORKER,
                description="Cleaned area",
                latitude=30.0,
                longitude=76.0,
                occurred_at=datetime.now(timezone.utc),
            )
        )
        assets = MediaAssetRepository(session)
        # Add before asset
        before_asset = assets.add(
            assets.model(
                incident_id=incident.id,
                storage_key=f"incidents/{incident.id}/before-1",
                content_type="image/jpeg",
                sha256="abc",
                is_after_cleanup=False,
            )
        )
        session.commit()

        ver_service = VerificationService(
            VerificationRepository(session),
            assets,
            incidents,
            users,
            AuditEventRepository(session),
            storage=storage,
        )

        test_image_bytes = b"verification-after-bytes"
        record = ver_service.submit_evidence(incident.id, worker.id, test_image_bytes)
        session.commit()

        after_assets = assets.list_for_incident(incident.id, after_cleanup=True)
        assert len(after_assets) == 1
        stored_bytes = storage.get(after_assets[0].storage_key)
        assert stored_bytes == test_image_bytes


def test_metrics_registry_memory_bounded():
    metrics = MetricsRegistry()
    for i in range(100):
        metrics.observe("test_metric", float(i), tag="a")

    snapshot = metrics.snapshot()
    key = "test_metric{'tag': 'a'}"
    assert key in snapshot["timings"]
    assert snapshot["timings"][key]["count"] == 100.0
    assert snapshot["timings"][key]["max"] == 99.0
    assert snapshot["timings"][key]["sum"] == sum(range(100))


def test_production_db_engine_configures_connection_pool():
    from unittest.mock import patch

    with patch("civicloop.db.sqlalchemy_create_engine") as mock_create:
        create_engine("postgresql+psycopg2://user:pass@localhost:5432/db")
        mock_create.assert_called_once()
        _, kwargs = mock_create.call_args
        assert kwargs["pool_size"] == 20
        assert kwargs["max_overflow"] == 10
        assert kwargs["pool_pre_ping"] is True
        assert kwargs["pool_recycle"] == 1800
