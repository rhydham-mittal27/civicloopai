# PilotService

## Repositories

- `EvaluationRunRepository`: planned `add`, `list`
- `IncidentRepository`: `list_by_status`, `list_for_location`
- `VerificationRepository`: `latest_for_incident`
- `RiskAssessmentRepository`: `ranked`
- `AuditEventRepository`: planned `add`

## Functions

### `start_pilot(name, location, start_date, end_date, baseline_version, actor_id)`

```text
require stakeholder approval and valid 8-12 week dates
baseline = EvaluationDataset.load(baseline_version, location)
run = EvaluationRun(name, baseline_version, metrics={}, baseline_metrics=baseline.metrics)
EvaluationRunRepository.add(run)
AuditEventRepository.add(actor_id, "evaluation_run", run.id, "pilot_started", {"location": location})
return run
```

### `collect_metrics(pilot_id)`

```text
incidents = IncidentRepository.list_by_status(VERIFIED)
risk_scores = RiskAssessmentRepository.ranked()
verified = [VerificationRepository.latest_for_incident(i.id) for i in incidents]
metrics = PilotMetrics.calculate(incidents, risk_scores, verified)
run = EvaluationRunRepository.get(pilot_id)
run.metrics = metrics
EvaluationRunRepository.update(run)
return metrics
```

### `close_pilot(pilot_id, actor_id)`

```text
metrics = collect_metrics(pilot_id)
require metrics include baseline comparisons
AuditEventRepository.add(actor_id, "evaluation_run", pilot_id, "pilot_closed", metrics)
return metrics
```