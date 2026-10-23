# EvaluationService

## Repositories

- `EvaluationRunRepository`: planned `add`, `get`, `list`
- `IncidentRepository`: `list_by_status`
- `AnalysisRepository`: `list_for_incident`
- `DuplicateClusterRepository`: planned `list`, `metrics`
- `RiskAssessmentRepository`: `ranked`
- `RoutePlanRepository`: planned `list`
- `VerificationRepository`: `latest_for_incident`
- `AuditEventRepository`: planned `add`

## Functions

### `run_evaluation(dataset_version, dataset, name)`

```text
fixtures = DatasetLoader.load(dataset, dataset_version)
extraction = Metrics.extraction_quality(fixtures, AnalysisRepository)
duplicates = Metrics.duplicate_precision_recall(fixtures, DuplicateClusterRepository)
risk = Metrics.ranking_quality(fixtures, RiskAssessmentRepository)
routes = Metrics.route_efficiency(fixtures, RoutePlanRepository)
closure = Metrics.verified_closure_rate(fixtures, VerificationRepository)
workflow = Metrics.workflow_reliability(fixtures, IncidentRepository)
baseline = DatasetLoader.baseline_metrics(dataset_version)
run = EvaluationRun(name, dataset_version,
                    metrics={extraction, duplicates, risk, routes, closure, workflow},
                    baseline_metrics=baseline)
EvaluationRunRepository.add(run)
AuditEventRepository.add(None, "evaluation_run", run.id, "completed", {"dataset": dataset_version})
return run
```

### `get_run(run_id)`

```text
return EvaluationRunRepository.get(run_id)
```

### `compare_with_baseline(run_id)`

```text
run = EvaluationRunRepository.get(run_id)
return Metrics.compare(run.metrics, run.baseline_metrics)
```