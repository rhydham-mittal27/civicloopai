# MunicipalIntegrationService

## Repositories

- Aggregate repository selected by payload: `IncidentRepository`, `WorkOrderRepository`, or `VerificationRepository`
- `AuditEventRepository`: planned `add`

## Functions

### `export_work_orders(work_order_ids, system_name, actor_id)`

```text
orders = [WorkOrderRepository.get(id) for id in work_order_ids]
require every order exists and actor has integration permission
payload = MunicipalMapper.to_work_order_payload(orders)
response = MunicipalAdapter(system_name).export_work_orders(payload)
AuditEventRepository.add(actor_id, "municipal_export", system_name, "completed", {"count": len(orders)})
return response
```

### `import_status_updates(system_name, updates, actor_id)`

```text
for update in updates:
    order = WorkOrderRepository.get(update.external_reference)
    require order exists or send to reconciliation queue
    validate allowed status transition
    order.status = map_external_status(update.status)
    AuditEventRepository.add(actor_id, "work_order", order.id, "status_imported", update)
return imported_count
```

Never overwrite local evidence or verification decisions without an explicit policy.