from __future__ import annotations

from datetime import datetime, timezone

from civicloop.models import (
    IncidentStatus,
    WorkOrderStatus,
    UserRole,
    VerificationRecord,
    VerificationStatus,
)
from civicloop.repositories import (
    AuditEventRepository,
    IncidentRepository,
    MediaAssetRepository,
    UserRepository,
    VerificationRepository,
    WorkOrderRepository,
)
from civicloop.services.common import NotFoundError, record_audit, require_user
from civicloop.storage import ObjectStorageAdapter


class VerificationService:
    def __init__(
        self,
        verifications: VerificationRepository,
        assets: MediaAssetRepository,
        incidents: IncidentRepository,
        users: UserRepository,
        audit: AuditEventRepository,
        storage: ObjectStorageAdapter | None = None,
        work_orders: WorkOrderRepository | None = None,
    ) -> None:
        self.work_orders = work_orders
        self.verifications = verifications
        self.assets = assets
        self.incidents = incidents
        self.users = users
        self.audit = audit
        self.storage = storage

    def submit_evidence(
        self,
        incident_id: str,
        worker_id: str,
        image: bytes,
        notes: str | None = None,
        content_type: str = "image/jpeg",
    ) -> VerificationRecord:
        require_user(self.users, worker_id, {UserRole.SANITATION_WORKER})
        incident = self.incidents.get(incident_id)
        if incident is None:
            raise NotFoundError(f"Incident not found: {incident_id}")
        before = self.assets.list_for_incident(incident_id, after_cleanup=False)
        if not before:
            raise ValueError("Before-cleanup evidence is required")
        if not image or not content_type.startswith("image/"):
            raise ValueError("A non-empty image is required")
        asset = self._store_after_image(incident_id, image, content_type)
        # Rule-based check, only clear cases pass: the work order is completed and the
        # after photo is not a copy of a before photo. Everything else needs a supervisor.
        differs_from_before = all(asset.sha256 != b.sha256 for b in before)
        order_done = self.work_orders is None or any(
            o.status == WorkOrderStatus.COMPLETED for o in self.work_orders.list_for_incident(incident_id)
        )
        status = (
            VerificationStatus.VERIFIED
            if differs_from_before and order_done
            else VerificationStatus.UNCERTAIN
        )
        record = self.verifications.add(
            VerificationRecord(
                incident_id=incident_id,
                submitted_by=worker_id,
                status=status,
                evidence_notes=notes,
            )
        )
        incident.status = (
            IncidentStatus.VERIFIED
            if status == VerificationStatus.VERIFIED
            else IncidentStatus.UNCERTAIN
        )
        record_audit(
            self.audit,
            worker_id,
            "verification",
            record.id,
            "submitted",
            {"status": status.value},
        )
        return record

    def review_evidence(
        self,
        record_id: str,
        supervisor_id: str,
        status: VerificationStatus,
        reason: str,
    ) -> VerificationRecord:
        require_user(self.users, supervisor_id, {UserRole.SUPERVISOR, UserRole.ADMIN})
        record = self.verifications.get(record_id)
        if record is None:
            raise NotFoundError(f"Verification record not found: {record_id}")
        if not reason.strip():
            raise ValueError("A reason is required to review evidence")
        record.status = status
        record.reviewed_by = supervisor_id
        record.review_reason = reason
        record.reviewed_at = datetime.now(timezone.utc)
        incident = self.incidents.get(record.incident_id)
        if incident is None:
            raise NotFoundError(f"Incident not found: {record.incident_id}")
        incident.status = {
            VerificationStatus.VERIFIED: IncidentStatus.VERIFIED,
            # A rejected cleanup goes back to the field for rework.
            VerificationStatus.REJECTED: IncidentStatus.IN_PROGRESS,
            VerificationStatus.UNCERTAIN: IncidentStatus.UNCERTAIN,
        }.get(status, IncidentStatus.UNCERTAIN)
        record_audit(
            self.audit,
            supervisor_id,
            "verification",
            record_id,
            "reviewed",
            {"status": status.value, "reason": reason},
        )
        return record

    def latest_verification(self, incident_id: str) -> VerificationRecord | None:
        return self.verifications.latest_for_incident(incident_id)

    def _store_after_image(self, incident_id: str, image: bytes, content_type: str = "image/jpeg"):
        import hashlib
        import uuid
        from civicloop.models import MediaAsset

        digest = hashlib.sha256(image).hexdigest()
        key = f"incidents/{incident_id}/after-{uuid.uuid4().hex[:8]}-{digest}"
        if self.storage is not None:
            self.storage.put(key, image, content_type)
        return self.assets.add(
            MediaAsset(
                incident_id=incident_id,
                storage_key=key,
                content_type=content_type,
                sha256=digest,
                is_after_cleanup=True,
            )
        )
