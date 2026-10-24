from __future__ import annotations

from civicloop.models import AnalysisResult, IncidentStatus
from civicloop.ai import AnalysisAdapter, validate_analysis_output
from civicloop.repositories import (
    AnalysisRepository,
    AuditEventRepository,
    IncidentRepository,
    MediaAssetRepository,
)
from civicloop.services.common import NotFoundError, record_audit
from civicloop.storage import ObjectStorageAdapter


class AnalysisService:
    def __init__(
        self,
        analyses: AnalysisRepository,
        incidents: IncidentRepository,
        assets: MediaAssetRepository,
        audit: AuditEventRepository,
        storage: ObjectStorageAdapter | None = None,
    ) -> None:
        self.analyses = analyses
        self.incidents = incidents
        self.assets = assets
        self.audit = audit
        self.storage = storage

    def analyze_incident(
        self, incident_id: str, adapter: AnalysisAdapter
    ) -> AnalysisResult:
        incident = self.incidents.get(incident_id)
        if incident is None:
            raise NotFoundError(f"Incident not found: {incident_id}")
        if incident.status != IncidentStatus.PENDING_ANALYSIS:
            raise ValueError("Incident is not waiting for analysis")
        payload = {
            "description": incident.description,
            "latitude": incident.latitude,
            "longitude": incident.longitude,
            "occurred_at": incident.occurred_at.isoformat(),
            "media": self._media_payload(incident_id),
        }
        raw = adapter.analyze(payload)
        raw = validate_analysis_output(raw)
        result = self.analyses.add(
            AnalysisResult(
                incident_id=incident_id,
                provider=adapter.provider,
                model_name=adapter.model_name,
                category=str(raw["category"]),
                severity=raw.get("severity"),
                confidence=raw.get("confidence"),
                extracted_details=raw.get("details", {}),
                raw_response=raw,
            )
        )
        incident.status = IncidentStatus.READY_FOR_REVIEW
        record_audit(
            self.audit,
            None,
            "incident",
            incident_id,
            "analyzed",
            {"provider": adapter.provider},
        )
        return result

    def latest_analysis(self, incident_id: str) -> AnalysisResult | None:
        return self.analyses.latest_for_incident(incident_id)

    def _media_payload(self, incident_id: str) -> list[object]:
        payload: list[object] = []
        for asset in self.assets.list_for_incident(incident_id, after_cleanup=False):
            if self.storage is None:
                payload.append(asset.storage_key)
                continue
            payload.append(
                {
                    "storage_key": asset.storage_key,
                    "content_type": asset.content_type,
                    "content": self.storage.get(asset.storage_key),
                }
            )
        return payload
