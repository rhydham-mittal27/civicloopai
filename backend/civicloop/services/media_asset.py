from __future__ import annotations

import hashlib
import uuid
from datetime import datetime

from civicloop.models import MediaAsset, UserRole
from civicloop.repositories import (
    AuditEventRepository,
    IncidentRepository,
    MediaAssetRepository,
    UserRepository,
)
from civicloop.services.common import NotFoundError, record_audit, require_user
from civicloop.storage import InMemoryObjectStorage, ObjectStorageAdapter, StorageIntegrityError


class MediaAssetService:
    def __init__(
        self,
        assets: MediaAssetRepository,
        incidents: IncidentRepository,
        users: UserRepository,
        audit: AuditEventRepository,
        storage: ObjectStorageAdapter | None = None,
    ) -> None:
        self.assets = assets
        self.incidents = incidents
        self.users = users
        self.audit = audit
        self.storage = storage or InMemoryObjectStorage()

    def store_for_incident(
        self,
        incident_id: str,
        image: bytes,
        content_type: str = "image/jpeg",
        captured_at: datetime | None = None,
        is_after_cleanup: bool = False,
        storage_key: str | None = None,
    ) -> MediaAsset:
        incident = self.incidents.get(incident_id)
        if incident is None:
            raise NotFoundError(f"Incident not found: {incident_id}")
        if not image or not content_type.startswith("image/"):
            raise ValueError("A non-empty image is required")
        digest = hashlib.sha256(image).hexdigest()
        key = storage_key or f"tenants/{incident.tenant_id}/incidents/{incident_id}/{uuid.uuid4()}/{digest}"
        stored = self.storage.put(key, image, content_type)
        if stored.sha256 != digest or stored.size_bytes != len(image):
            self.storage.delete(key)
            raise StorageIntegrityError("Stored object does not match uploaded content")
        try:
            return self.assets.add(
                MediaAsset(
                    incident_id=incident_id,
                    storage_key=stored.key,
                    content_type=stored.content_type,
                    sha256=stored.sha256,
                    captured_at=captured_at,
                    is_after_cleanup=is_after_cleanup,
                )
            )
        except Exception:
            if self.storage.exists(key):
                self.storage.delete(key)
            raise

    def list_evidence(
        self, incident_id: str, after_cleanup: bool | None = None
    ) -> list[MediaAsset]:
        if self.incidents.get(incident_id) is None:
            raise NotFoundError(f"Incident not found: {incident_id}")
        return list(
            self.assets.list_for_incident(incident_id, after_cleanup=after_cleanup)
        )

    def delete_asset(self, asset_id: str, actor_id: str) -> None:
        require_user(self.users, actor_id, {UserRole.ADMIN})
        asset = self.assets.get(asset_id)
        if asset is None:
            raise NotFoundError(f"Media asset not found: {asset_id}")
        self.storage.delete(asset.storage_key)
        self.assets.delete(asset)
        record_audit(self.audit, actor_id, "media_asset", asset_id, "deleted")

    def create_read_url(self, asset_id: str, expires_seconds: int = 900) -> str:
        asset = self.assets.get(asset_id)
        if asset is None:
            raise NotFoundError(f"Media asset not found: {asset_id}")
        return self.storage.create_read_url(asset.storage_key, expires_seconds)
