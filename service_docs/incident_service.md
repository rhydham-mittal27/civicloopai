# IncidentService

## Repositories

- `IncidentRepository`: `get`, `add`, `list_by_status`, `list_for_location`
- `UserRepository`: `get`
- `MediaAssetRepository`: planned `add`, `list_for_incident`
- `AuditEventRepository`: planned `add`

## Functions

### `create_incident(reporter_id, reporter_type, description, latitude, longitude, occurred_at, media_input)`

```text
reporter = UserRepository.get(reporter_id)
require reporter is active and reporter.role permits reporting
validate description, coordinates, timestamp, and image type/size
incident = Incident(..., status=PENDING_ANALYSIS)
IncidentRepository.add(incident)
for image in media_input:
    asset = MediaAssetService.store_for_incident(incident.id, image, is_after_cleanup=False)
AuditEventRepository.add(reporter_id, "incident", incident.id, "created", {})
return incident
```

### `get_incident(incident_id)`

```text
incident = IncidentRepository.get(incident_id)
if incident is None: raise NotFoundError
return incident
```

### `list_incidents(status=None, location=None, limit=None)`

```text
if status is provided: return IncidentRepository.list_by_status(status, limit=limit)
if location is provided: return IncidentRepository.list_for_location(lat, lon, limit=limit)
return IncidentRepository.list_by_status(READY_FOR_REVIEW, limit=limit)
```

### `change_status(incident_id, new_status, actor_id)`

```text
incident = IncidentRepository.get(incident_id)
require transition is allowed and actor has permission
incident.status = new_status
AuditEventRepository.add(actor_id, "incident", incident_id, "status_changed", {"status": new_status})
return incident
```