# PrioritizationService

## Repositories

- `RiskAssessmentRepository`: `ranked`, `latest_for_incident`
- `IncidentRepository`: `get`, `list_by_status`
- `WorkOrderRepository`: `list_for_incident`
- `AuditEventRepository`: planned `add`

## Functions

### `build_queue(limit=None, status=READY_FOR_REVIEW)`

```text
ranked = RiskAssessmentRepository.ranked(limit=limit)
queue = []
for assessment in ranked:
    incident = IncidentRepository.get(assessment.incident_id)
    if incident is not None and incident.status == status:
        existing = WorkOrderRepository.list_for_incident(incident.id)
        queue.append({incident, assessment, existing})
return queue
```

### `apply_override(incident_id, supervisor_id, priority, reason)`

```text
require supervisor role
incident = IncidentRepository.get(incident_id)
require incident exists
order = latest_or_create_work_order(incident_id)
order.priority = priority
order.override_reason = reason
AuditEventRepository.add(supervisor_id, "work_order", order.id, "priority_overridden", {"reason": reason})
return order
```

### `get_queue_item(incident_id)`

```text
incident = IncidentRepository.get(incident_id)
assessment = RiskAssessmentRepository.latest_for_incident(incident_id)
orders = WorkOrderRepository.list_for_incident(incident_id)
return {incident, assessment, orders}
```