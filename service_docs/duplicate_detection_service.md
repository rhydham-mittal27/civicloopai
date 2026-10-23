# DuplicateDetectionService

## Repositories

- `DuplicateClusterRepository`: planned `add`, `get`, `add_member`, `confirm`, `reject`
- `IncidentRepository`: `get`, `list_for_location`
- `AnalysisRepository`: `latest_for_incident`
- `AuditEventRepository`: planned `add`

## Functions

### `find_candidates(incident_id, radius_degrees=0.01, limit=50)`

```text
incident = IncidentRepository.get(incident_id)
require incident exists
candidates = IncidentRepository.list_for_location(incident.latitude, incident.longitude,
                                                   radius_degrees=radius_degrees, limit=limit)
for candidate in candidates excluding incident_id:
    compare time window, description, latest analyses, and image similarity
    keep candidate when combined score >= configured threshold
return candidates ordered by similarity score descending
```

### `create_candidate_cluster(incident_id, candidate_scores)`

```text
cluster = DuplicateCluster(confirmed=False)
DuplicateClusterRepository.add(cluster)
DuplicateClusterRepository.add_member(cluster.id, incident_id, 1.0)
for candidate_id, score in candidate_scores:
    DuplicateClusterRepository.add_member(cluster.id, candidate_id, score)
AuditEventRepository.add(None, "duplicate_cluster", cluster.id, "created", {})
return cluster
```

### `confirm_cluster(cluster_id, supervisor_id)`

```text
require supervisor role
cluster = DuplicateClusterRepository.get(cluster_id)
require cluster exists
DuplicateClusterRepository.confirm(cluster_id, supervisor_id)
AuditEventRepository.add(supervisor_id, "duplicate_cluster", cluster_id, "confirmed", {})
return cluster
```

Never delete or merge away source incidents.