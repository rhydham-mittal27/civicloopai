# AnalysisService

## Repositories

- `AnalysisRepository`: `add`, `latest_for_incident`, `list_for_incident`
- `IncidentRepository`: `get`
- `MediaAssetRepository`: planned `list_for_incident`
- `AuditEventRepository`: planned `add`

## Functions

### `analyze_incident(incident_id, provider="gemini")`

```text
incident = IncidentRepository.get(incident_id)
require incident exists and status == PENDING_ANALYSIS
assets = MediaAssetRepository.list_for_incident(incident_id, after_cleanup=False)
payload = {description, coordinates, occurred_at, assets}
raw = selected_model_adapter(provider).analyze(payload)
result = SchemaValidator.parse_analysis(raw)
analysis = AnalysisResult(provider, model_name, category, severity,
                          confidence, extracted_details, raw_response)
AnalysisRepository.add(analysis)
incident.status = READY_FOR_REVIEW
AuditEventRepository.add(None, "incident", incident_id, "analyzed", {"provider": provider})
return analysis
```

### `latest_analysis(incident_id)`

```text
return AnalysisRepository.latest_for_incident(incident_id)
```

### `reanalyze_incident(incident_id, provider)`

```text
require IncidentRepository.get(incident_id) exists
return analyze_incident(incident_id, provider)
```

On adapter or schema failure, do not change the incident status; enqueue a retryable job and record the failure in the worker log.