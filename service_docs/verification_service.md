# VerificationService

## Repositories

- `VerificationRepository`: `add`, `get`, `latest_for_incident`
- `MediaAssetRepository`: planned `add`, `list_for_incident`
- `IncidentRepository`: `get`
- `UserRepository`: `get`
- `AuditEventRepository`: planned `add`

## Functions

### `submit_evidence(incident_id, worker_id, image, notes=None)`

```text
incident = IncidentRepository.get(incident_id)
worker = UserRepository.get(worker_id)
require incident exists and worker is active sanitation worker
asset = MediaAssetService.store_for_incident(incident_id, image, is_after_cleanup=True)
record = VerificationRecord(incident_id, submitted_by=worker_id, status=PENDING,
                            evidence_notes=notes)
VerificationRepository.add(record)
decision = VerificationRules.compare_before_after(incident, asset)
if decision.is_clear:
    record.status = VERIFIED
    incident.status = VERIFIED
else:
    record.status = UNCERTAIN
    incident.status = UNCERTAIN
AuditEventRepository.add(worker_id, "verification", record.id, "submitted", {"status": record.status})
return record
```

### `review_evidence(record_id, supervisor_id, status, reason)`

```text
require supervisor role
record = VerificationRepository.get(record_id)
require record exists and status in {VERIFIED, UNCERTAIN, REJECTED}
record.status = status
record.reviewed_by = supervisor_id
record.review_reason = reason
incident = IncidentRepository.get(record.incident_id)
incident.status = status_to_incident_status(status)
AuditEventRepository.add(supervisor_id, "verification", record_id, "reviewed", {"reason": reason})
return record
```

### `latest_verification(incident_id)`

```text
return VerificationRepository.latest_for_incident(incident_id)
```