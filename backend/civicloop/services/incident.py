from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from civicloop.tenancy import normalise_pincode
from civicloop.models import Incident, IncidentStatus, ReporterType, UserRole
from civicloop.repositories import (
    AuditEventRepository,
    IncidentRepository,
    UserRepository,
)
from civicloop.services.common import NotFoundError, record_audit, require_user


class IncidentService:
    def __init__(
        self,
        incidents: IncidentRepository,
        users: UserRepository,
        audit: AuditEventRepository,
    ) -> None:
        self.incidents = incidents
        self.users = users
        self.audit = audit

    def create_incident(
        self,
        reporter_id: str,
        reporter_type: ReporterType,
        description: str,
        latitude: float,
        longitude: float,
        occurred_at: datetime,
        pincode: str | None = None,
        client_key: str | None = None,
    ) -> Incident:
        reporter = require_user(
            self.users,
            reporter_id,
            {UserRole.REPORTER, UserRole.SUPERVISOR, UserRole.SANITATION_WORKER},
        )
        if (
            not description.strip()
            or not -90 <= latitude <= 90
            or not -180 <= longitude <= 180
        ):
            raise ValueError("Description and valid coordinates are required")
        incident = self.incidents.add(
            Incident(
                reporter_id=reporter_id,
                reporter_type=reporter_type,
                client_key=client_key,
                description=description.strip(),
                latitude=latitude,
                longitude=longitude,
                pincode=normalise_pincode(pincode) or reporter.pincode,
                tenant_id=reporter.tenant_id,
                occurred_at=occurred_at,
                status=IncidentStatus.PENDING_ANALYSIS,
            )
        )
        record_audit(self.audit, reporter_id, "incident", incident.id, "created")
        return incident

    def get_incident(self, incident_id: str) -> Incident:
        incident = self.incidents.get(incident_id)
        if incident is None:
            raise NotFoundError(f"Incident not found: {incident_id}")
        return incident

    def list_incidents(
        self,
        status: IncidentStatus | None = None,
        location: tuple[float, float] | None = None,
        limit: int | None = None,
    ) -> Sequence[Incident]:
        if status is not None:
            return self.incidents.list_by_status(status, limit=limit)
        if location is not None:
            return self.incidents.list_for_location(*location, limit=limit)
        return self.incidents.list_by_status(
            IncidentStatus.READY_FOR_REVIEW, limit=limit
        )

    def change_status(
        self, incident_id: str, new_status: IncidentStatus, actor_id: str
    ) -> Incident:
        require_user(self.users, actor_id, {UserRole.SUPERVISOR, UserRole.ADMIN})
        incident = self.get_incident(incident_id)
        incident.status = new_status
        record_audit(
            self.audit,
            actor_id,
            "incident",
            incident_id,
            "status_changed",
            {"status": new_status.value},
        )
        return incident
