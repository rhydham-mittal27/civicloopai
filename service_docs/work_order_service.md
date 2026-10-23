# WorkOrderService

## Repositories

- `WorkOrderRepository`: `add`, `get`, `list_by_status`, `list_for_incident`
- `IncidentRepository`: `get`
- `UserRepository`: `get`
- `AuditEventRepository`: planned `add`

## Functions

### `create_order(incident_id, priority, estimated_volume, actor_id)`

```text
actor = UserRepository.get(actor_id)
incident = IncidentRepository.get(incident_id)
require actor is supervisor and incident.status == READY_FOR_REVIEW
order = WorkOrder(incident_id, priority, estimated_volume, status=DRAFT)
WorkOrderRepository.add(order)
AuditEventRepository.add(actor_id, "work_order", order.id, "created", {})
return order
```

### `approve_order(order_id, supervisor_id)`

```text
order = WorkOrderRepository.get(order_id)
require supervisor and order.status == DRAFT
order.status = APPROVED
incident = IncidentRepository.get(order.incident_id)
incident.status = APPROVED
AuditEventRepository.add(supervisor_id, "work_order", order_id, "approved", {})
return order
```

### `assign_order(order_id, worker_id, supervisor_id)`

```text
require supervisor role
worker = UserRepository.get(worker_id)
require worker.role == SANITATION_WORKER and worker.is_active
order = WorkOrderRepository.get(order_id)
require order.status == APPROVED
order.assigned_to = worker_id
order.status = ASSIGNED
AuditEventRepository.add(supervisor_id, "work_order", order_id, "assigned", {"worker_id": worker_id})
return order
```

### `complete_order(order_id, worker_id)`

```text
order = WorkOrderRepository.get(order_id)
require order.assigned_to == worker_id and order.status in {ASSIGNED, IN_PROGRESS}
order.status = COMPLETED
AuditEventRepository.add(worker_id, "work_order", order_id, "completed", {})
return order
```

Completion does not verify cleanup; `VerificationService` must do that.