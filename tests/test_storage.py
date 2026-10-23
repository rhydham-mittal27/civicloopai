from datetime import datetime, timezone
from pathlib import Path

import pytest

from civicloop.storage import (
    InMemoryObjectStorage,
    InvalidStorageKey,
    LocalFilesystemObjectStorage,
    StorageObjectNotFound,
)
from civicloop.db import init_db
from civicloop.models import Incident, ReporterType, User, UserRole
from civicloop.repositories import AuditEventRepository, IncidentRepository, MediaAssetRepository, UserRepository
from civicloop.services.media_asset import MediaAssetService
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_memory_storage_round_trip_and_read_url():
    storage = InMemoryObjectStorage()
    stored = storage.put("incidents/one/image.jpg", b"image", "image/jpeg")

    assert stored.size_bytes == 5
    assert storage.get(stored.key) == b"image"
    assert storage.exists(stored.key)
    assert storage.create_read_url(stored.key).startswith("memory://")


def test_local_storage_round_trip_and_cleanup(tmp_path: Path):
    storage = LocalFilesystemObjectStorage(tmp_path)
    stored = storage.put("incidents/one/image.jpg", b"image", "image/jpeg")

    assert (tmp_path / "incidents" / "one" / "image.jpg").read_bytes() == b"image"
    assert storage.get(stored.key) == b"image"
    storage.delete(stored.key)
    assert not storage.exists(stored.key)
    with pytest.raises(StorageObjectNotFound):
        storage.get(stored.key)


def test_storage_rejects_path_traversal(tmp_path: Path):
    storage = LocalFilesystemObjectStorage(tmp_path)

    with pytest.raises(InvalidStorageKey):
        storage.put("../outside.jpg", b"image", "image/jpeg")


def test_local_storage_does_not_leave_partial_files(tmp_path: Path):
    storage = LocalFilesystemObjectStorage(tmp_path)
    storage.put("nested/image.jpg", b"first", "image/jpeg")
    storage.put("nested/image.jpg", b"second", "image/jpeg")

    assert storage.get("nested/image.jpg") == b"second"
    assert not list(tmp_path.rglob("*.tmp"))


def test_media_service_uploads_and_deletes_object():
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)
    storage = InMemoryObjectStorage()
    with Session(engine) as session:
        users = UserRepository(session)
        incidents = IncidentRepository(session)
        assets = MediaAssetRepository(session)
        reporter = users.add(User(name="Reporter", email="storage@example.com", role=UserRole.REPORTER))
        admin = users.add(User(name="Admin", email="storage-admin@example.com", role=UserRole.ADMIN))
        incident = incidents.add(Incident(reporter_id=reporter.id, reporter_type=ReporterType.RESIDENT, description="Waste", latitude=1, longitude=1, occurred_at=datetime.now(timezone.utc)))
        service = MediaAssetService(assets, incidents, users, AuditEventRepository(session), storage)
        asset = service.store_for_incident(incident.id, b"image")
        assert storage.exists(asset.storage_key)
        service.delete_asset(asset.id, admin.id)
        assert not storage.exists(asset.storage_key)


def test_media_service_cleans_object_when_database_write_fails():
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)
    storage = InMemoryObjectStorage()
    with Session(engine) as session:
        users = UserRepository(session)
        incidents = IncidentRepository(session)
        reporter = users.add(User(name="Reporter", email="failure@example.com", role=UserRole.REPORTER))
        incident = incidents.add(Incident(reporter_id=reporter.id, reporter_type=ReporterType.RESIDENT, description="Waste", latitude=1, longitude=1, occurred_at=datetime.now(timezone.utc)))

        class FailingAssetRepository(MediaAssetRepository):
            def add(self, entity):
                raise RuntimeError("database unavailable")

        service = MediaAssetService(FailingAssetRepository(session), incidents, users, AuditEventRepository(session), storage)
        with pytest.raises(RuntimeError, match="database unavailable"):
            service.store_for_incident(incident.id, b"image")
        assert storage._objects == {}