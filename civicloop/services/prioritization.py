from __future__ import annotations

from civicloop.models import IncidentStatus, UserRole
from civicloop.repositories import (
    AuditEventRepository,
    IncidentRepository,
    RiskAssessmentRepository,
    WorkOrderRepository,
)
from civicloop.services.common import NotFoundError, record_audit, require_user


class PrioritizationService:
    def __init__(
        self,
        risks: RiskAssessmentRepository,
        incidents: IncidentRepository,
        work_orders: WorkOrderRepository,
        users,
        audit: AuditEventRepository,
    ) -> None:
        self.risks = risks
        self.incidents = incidents
        self.work_orders = work_orders
        self.users = users
        self.audit = audit

    def build_queue(
        self,
        limit: int | None = None,
        status: IncidentStatus = IncidentStatus.READY_FOR_REVIEW,
    ) -> list[dict[str, object]]:
        """Incidents in `status`, highest latest risk first; unscored incidents go last."""
        queue = []
        for incident in self.incidents.list_by_status(status):
            queue.append(
                {
                    "incident": incident,
                    "risk": self.risks.latest_for_incident(incident.id),
                    "work_orders": self.work_orders.list_for_incident(incident.id),
                }
            )
        queue.sort(
            key=lambda item: (
                item["risk"] is None,
                -(item["risk"].score if item["risk"] is not None else 0.0),
                item["incident"].created_at,
            )
        )
        return queue[:limit] if limit is not None else queue

    def apply_override(
        self, incident_id: str, supervisor_id: str, priority: int, reason: str
    ):
        require_user(self.users, supervisor_id, {UserRole.SUPERVISOR, UserRole.ADMIN})
        incident = self.incidents.get(incident_id)
        if incident is None:
            raise NotFoundError(f"Incident not found: {incident_id}")
        orders = self.work_orders.list_for_incident(incident_id)
        if not orders:
            raise ValueError(
                "A work order must exist before applying a priority override"
            )
        if not reason.strip():
            raise ValueError("A reason is required for a priority override")
        order = next((o for o in orders if o.status.value != "cancelled"), orders[0])
        order.priority = priority
        order.override_reason = reason
        record_audit(
            self.audit,
            supervisor_id,
            "work_order",
            order.id,
            "priority_overridden",
            {"reason": reason},
        )
        return order

    def get_queue_item(self, incident_id: str) -> dict[str, object]:
        incident = self.incidents.get(incident_id)
        if incident is None:
            raise NotFoundError(f"Incident not found: {incident_id}")
        return {
            "incident": incident,
            "risk": self.risks.latest_for_incident(incident_id),
            "work_orders": self.work_orders.list_for_incident(incident_id),
        }
