# HotspotRiskService

## Repositories

- `RiskAssessmentRepository`: `add`, `latest_for_incident`, `ranked`
- `IncidentRepository`: `get`, `list_for_location`
- `AnalysisRepository`: `latest_for_incident`
- `AuditEventRepository`: planned `add`

## Functions

### `calculate_risk(incident_id, model_version="baseline-1")`

```text
incident = IncidentRepository.get(incident_id)
require incident exists
history = IncidentRepository.list_for_location(incident.latitude, incident.longitude)
analysis = AnalysisRepository.latest_for_incident(incident_id)
factors = {
  recurrence: count(history),
  recent_incidents: count_within_window(history),
  severity: severity_value(analysis),
  time_decay: calculate_time_decay(history),
}
score = RiskScoringEngine.score(factors)
assessment = RiskAssessment(incident_id, score, confidence_from(factors), factors, model_version)
RiskAssessmentRepository.add(assessment)
AuditEventRepository.add(None, "incident", incident_id, "risk_scored", {"score": score})
return assessment
```

### `rank_incidents(limit=None)`

```text
assessments = RiskAssessmentRepository.ranked(limit=limit)
return [assessment for assessment in assessments if IncidentRepository.get(assessment.incident_id)]
```

### `latest_risk(incident_id)`

```text
return RiskAssessmentRepository.latest_for_incident(incident_id)
```