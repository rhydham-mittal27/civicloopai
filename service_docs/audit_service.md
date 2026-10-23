# AuditService

## Repositories

- `AuditEventRepository`: planned `add`, `list_for_entity`, `list_for_actor`

## Functions

### `record(actor_id, entity_type, entity_id, action, details)`

```text
validate entity_type, action, and JSON-serializable details
event = AuditEvent(actor_id, entity_type, entity_id, action, details)
AuditEventRepository.add(event)
return event
```

### `history(entity_type, entity_id)`

```text
return AuditEventRepository.list_for_entity(entity_type, entity_id)
```

### `actor_history(actor_id)`

```text
return AuditEventRepository.list_for_actor(actor_id)
```

Audit events are append-only. Services must not update or delete them.