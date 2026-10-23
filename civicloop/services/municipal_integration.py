from __future__ import annotations

from typing import Any, Protocol

from civicloop.models import UserRole, WorkOrderStatus
from civicloop.repositories import AuditEventRepository, WorkOrderRepository
from civicloop.services.common import record_audit, require_user


class MunicipalAdapter(Protocol):
    def export_work_orders(self, payload: list[dict[str, Any]]) -> Any: ...
    def import_status_updates(
        self, updates: list[dict[str, Any]]
    ) -> list[dict[str, Any]]: ...


class MunicipalIntegrationService:
    def __init__(
        self, work_orders: WorkOrderRepository, users, audit: AuditEventRepository
    ) -> None:
        self.work_orders = work_orders
        self.users = users
        self.audit = audit

    def export_work_orders(
        self,
        work_order_ids: list[str],
        system_name: str,
        actor_id: str,
        adapter: MunicipalAdapter,
    ) -> Any:
        require_user(self.users, actor_id, {UserRole.ADMIN, UserRole.SUPERVISOR})
        orders = [self.work_orders.get(order_id) for order_id in work_order_ids]
        if any(order is None for order in orders):
            raise ValueError("Every work order must exist")
        payload = [
            {
                "id": order.id,
                "incident_id": order.incident_id,
                "status": order.status.value,
                "priority": order.priority,
            }
            for order in orders
            if order is not None
        ]
        response = adapter.export_work_orders(payload)
        record_audit(
            self.audit,
            actor_id,
            "municipal_export",
            system_name,
            "completed",
            {"count": len(payload)},
        )
        return response

    def import_status_updates(
        self,
        updates: list[dict[str, Any]],
        system_name: str,
        actor_id: str,
        adapter: MunicipalAdapter,
    ) -> int:
        require_user(self.users, actor_id, {UserRole.ADMIN, UserRole.SUPERVISOR})
        imported = 0
        for update in adapter.import_status_updates(updates):
            order = self.work_orders.get(update["work_order_id"])
            if order is None:
                continue
            try:
                order.status = WorkOrderStatus(update["status"])
            except ValueError:
                continue
            imported += 1
            record_audit(
                self.audit,
                actor_id,
                "work_order",
                order.id,
                "status_imported",
                {"system": system_name},
            )
        return imported



class ManualMunicipalAdapter:
    """No external system configured: export hands the payload back for download,
    and import trusts the status updates the supervisor supplies."""

    def export_work_orders(self, payload: list[dict[str, Any]]) -> Any:
        return {"format": "civicloop-work-orders-v1", "work_orders": payload}

    def import_status_updates(self, updates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return updates
