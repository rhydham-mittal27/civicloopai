from __future__ import annotations

from civicloop.models import IncidentStatus, UserRole, WorkOrder, WorkOrderStatus
from civicloop.repositories import (
    AuditEventRepository,
    IncidentRepository,
    UserRepository,
    WorkOrderRepository,
)
from civicloop.services.common import NotFoundError, record_audit, require_user


class WorkOrderService:
    def __init__(
        self,
        work_orders: WorkOrderRepository,
        incidents: IncidentRepository,
        users: UserRepository,
        audit: AuditEventRepository,
    ) -> None:
        self.work_orders = work_orders
        self.incidents = incidents
        self.users = users
        self.audit = audit

    def create_order(
        self,
        incident_id: str,
        priority: int,
        estimated_volume: float | None,
        actor_id: str,
    ) -> WorkOrder:
        require_user(self.users, actor_id, {UserRole.SUPERVISOR, UserRole.ADMIN})
        incident = self.incidents.get(incident_id)
        if incident is None:
            raise NotFoundError(f"Incident not found: {incident_id}")
        if incident.status != IncidentStatus.READY_FOR_REVIEW:
            raise ValueError("Incident is not ready for work-order creation")
        if any(o.status != WorkOrderStatus.CANCELLED for o in self.work_orders.list_for_incident(incident_id)):
            raise ValueError("This incident already has an active work order")
        if estimated_volume is not None and estimated_volume < 0:
            raise ValueError("Estimated volume cannot be negative")
        order = self.work_orders.add(
            WorkOrder(
                incident_id=incident_id,
                priority=priority,
                estimated_volume=estimated_volume,
                status=WorkOrderStatus.DRAFT,
            )
        )
        record_audit(self.audit, actor_id, "work_order", order.id, "created")
        return order

    def approve_order(self, order_id: str, supervisor_id: str) -> WorkOrder:
        require_user(self.users, supervisor_id, {UserRole.SUPERVISOR, UserRole.ADMIN})
        order = self._get(order_id)
        if order.status != WorkOrderStatus.DRAFT:
            raise ValueError("Only draft work orders can be approved")
        incident = self.incidents.get(order.incident_id)
        if incident.status != IncidentStatus.READY_FOR_REVIEW:
            raise ValueError("Incident is no longer ready for review")
        order.status = WorkOrderStatus.APPROVED
        order.approved_by = supervisor_id
        incident.status = IncidentStatus.APPROVED
        record_audit(self.audit, supervisor_id, "work_order", order_id, "approved")
        return order

    def assign_order(
        self, order_id: str, worker_id: str, supervisor_id: str
    ) -> WorkOrder:
        require_user(self.users, supervisor_id, {UserRole.SUPERVISOR, UserRole.ADMIN})
        worker = require_user(self.users, worker_id, {UserRole.SANITATION_WORKER})
        order = self._get(order_id)
        if order.status != WorkOrderStatus.APPROVED:
            raise ValueError("Only approved work orders can be assigned")
        order.assigned_to = worker.id
        order.status = WorkOrderStatus.ASSIGNED
        record_audit(
            self.audit,
            supervisor_id,
            "work_order",
            order_id,
            "assigned",
            {"worker_id": worker_id},
        )
        return order

    def start_order(self, order_id: str, worker_id: str) -> WorkOrder:
        require_user(self.users, worker_id, {UserRole.SANITATION_WORKER})
        order = self._get(order_id)
        if order.assigned_to != worker_id or order.status != WorkOrderStatus.ASSIGNED:
            raise ValueError("Worker is not assigned to this order, or it was already started")
        order.status = WorkOrderStatus.IN_PROGRESS
        self.incidents.get(order.incident_id).status = IncidentStatus.IN_PROGRESS
        record_audit(self.audit, worker_id, "work_order", order_id, "started")
        return order

    def reopen_order(self, order_id: str, supervisor_id: str, reason: str) -> WorkOrder:
        require_user(self.users, supervisor_id, {UserRole.SUPERVISOR, UserRole.ADMIN})
        order = self._get(order_id)
        if order.status != WorkOrderStatus.COMPLETED:
            raise ValueError("Only completed work orders can be reopened")
        order.status = WorkOrderStatus.IN_PROGRESS
        self.incidents.get(order.incident_id).status = IncidentStatus.IN_PROGRESS
        record_audit(self.audit, supervisor_id, "work_order", order_id, "reopened", {"reason": reason})
        return order

    def complete_order(self, order_id: str, worker_id: str) -> WorkOrder:
        require_user(self.users, worker_id, {UserRole.SANITATION_WORKER})
        order = self._get(order_id)
        if order.assigned_to != worker_id or order.status not in {
            WorkOrderStatus.ASSIGNED,
            WorkOrderStatus.IN_PROGRESS,
        }:
            raise ValueError("Worker is not assigned to this active order")
        order.status = WorkOrderStatus.COMPLETED
        self.incidents.get(order.incident_id).status = IncidentStatus.RESOLVED
        record_audit(self.audit, worker_id, "work_order", order_id, "completed")
        return order

    def get(self, order_id: str) -> WorkOrder:
        return self._get(order_id)

    def _get(self, order_id: str) -> WorkOrder:
        order = self.work_orders.get(order_id)
        if order is None:
            raise NotFoundError(f"Work order not found: {order_id}")
        return order
