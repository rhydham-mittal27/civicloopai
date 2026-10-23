# CivicLoopAI API Route Plan

## 1. API Purpose

This route plan exposes the CivicLoopAI workflow described in the PPT:

`Observe -> Understand -> Predict -> Prioritize -> Act -> Verify -> Learn`

The current repository and service layers exist, but HTTP routers have not been implemented yet. These routes are the contract for the API layer that will call the services in `civicloop/services` and commit one transaction after each successful service operation.

## 2. API Conventions

- Base URL: `/api/v1`
- Format: JSON unless the request uploads an image.
- Authentication: bearer token; the API resolves `current_user_id` and role before calling a service.
- IDs: UUID strings.
- Time: ISO 8601 UTC timestamps.
- Coordinates: decimal latitude and longitude in WGS84.
- Pagination: `limit` and `offset` for list endpoints; default `limit=50`, maximum `limit=200`.
- Images: `multipart/form-data`, accepted content types are configured by the media service.
- Writes return the persisted resource and its current status.
- Long-running AI, evaluation, route, and integration operations may return `202 Accepted` with a job identifier.
- Every user decision, approval, override, assignment, import, and verification is written to the audit trail.

## 3. Roles

| Role | Main API capabilities |
| --- | --- |
| `reporter` | Create incidents, attach initial evidence, view own reports. |
| `supervisor` | Review all incidents, confirm duplicates, score/rank incidents, approve work, routes, and verification decisions. |
| `sanitation_worker` | View assigned work, complete work, submit after-cleanup evidence. |
| `admin` | Manage users, configuration, integrations, audit access, and all supervisor capabilities. |

## 4. Route Inventory

### Health and API metadata

| Method | Route | Auth | Service |
| --- | --- | --- | --- |
| `GET` | `/health` | Public | None |
| `GET` | `/api/v1` | Public | None |

### Users

| Method | Route | Auth | Service method |
| --- | --- | --- | --- |
| `POST` | `/users` | Admin or bootstrap | `UserService.create_user` |
| `GET` | `/users/{user_id}` | Authenticated | `UserService.get_user` |
| `GET` | `/users/by-email` | Admin | `UserService.get_user_by_email` |
| `POST` | `/users/{user_id}/deactivate` | Admin | `UserService.deactivate_user` |

### Incidents and media

| Method | Route | Auth | Service method |
| --- | --- | --- | --- |
| `POST` | `/incidents` | Reporter, supervisor, worker | `IncidentService.create_incident` |
| `GET` | `/incidents` | Authenticated | `IncidentService.list_incidents` |
| `GET` | `/incidents/{incident_id}` | Authenticated | `IncidentService.get_incident` |
| `PATCH` | `/incidents/{incident_id}/status` | Supervisor or admin | `IncidentService.change_status` |
| `POST` | `/incidents/{incident_id}/media` | Reporter, supervisor, worker | `MediaAssetService.store_for_incident` |
| `GET` | `/incidents/{incident_id}/media` | Authenticated | `MediaAssetService.list_evidence` |
| `DELETE` | `/media/{asset_id}` | Admin | `MediaAssetService.delete_asset` |

### Understand: AI analysis

| Method | Route | Auth | Service method |
| --- | --- | --- | --- |
| `POST` | `/incidents/{incident_id}/analysis` | Worker or supervisor job | `AnalysisService.analyze_incident` |
| `GET` | `/incidents/{incident_id}/analysis` | Authenticated | `AnalysisService.latest_analysis` and history repository query |

The analysis route selects a configured `GeminiAdapter` or `OpenWeightModelAdapter`. The adapter response must be schema-validated before `AnalysisService` persists it.

### Predict: duplicates and hotspot risk

| Method | Route | Auth | Service method |
| --- | --- | --- | --- |
| `GET` | `/incidents/{incident_id}/duplicate-candidates` | Supervisor | `DuplicateDetectionService.find_candidates` |
| `POST` | `/incidents/{incident_id}/duplicate-clusters` | Supervisor | `DuplicateDetectionService.create_candidate_cluster` |
| `POST` | `/duplicate-clusters/{cluster_id}/confirm` | Supervisor | `DuplicateDetectionService.confirm_cluster` |
| `POST` | `/duplicate-clusters/{cluster_id}/reject` | Supervisor | `DuplicateDetectionService.reject_cluster` |
| `POST` | `/incidents/{incident_id}/risk-assessments` | Worker or supervisor job | `HotspotRiskService.calculate_risk` |
| `GET` | `/incidents/{incident_id}/risk-assessments/latest` | Authenticated | `HotspotRiskService.latest_risk` |
| `GET` | `/risk-assessments/ranked` | Supervisor | `HotspotRiskService.rank_incidents` |

### Prioritize and act: work orders

| Method | Route | Auth | Service method |
| --- | --- | --- | --- |
| `GET` | `/prioritization/queue` | Supervisor | `PrioritizationService.build_queue` |
| `GET` | `/prioritization/incidents/{incident_id}` | Supervisor | `PrioritizationService.get_queue_item` |
| `POST` | `/incidents/{incident_id}/priority-override` | Supervisor | `PrioritizationService.apply_override` |
| `POST` | `/work-orders` | Supervisor | `WorkOrderService.create_order` |
| `GET` | `/work-orders` | Supervisor or worker | Repository status query |
| `GET` | `/work-orders/{work_order_id}` | Supervisor or assigned worker | Repository `get` |
| `POST` | `/work-orders/{work_order_id}/approve` | Supervisor | `WorkOrderService.approve_order` |
| `POST` | `/work-orders/{work_order_id}/assign` | Supervisor | `WorkOrderService.assign_order` |
| `POST` | `/work-orders/{work_order_id}/complete` | Assigned worker | `WorkOrderService.complete_order` |

Work completion does not mark an incident verified. Verification requires the separate evidence route below.

### Route planning

| Method | Route | Auth | Service method |
| --- | --- | --- | --- |
| `POST` | `/route-plans` | Supervisor | `RoutePlanningService.build_route` |
| `GET` | `/route-plans` | Supervisor | `RoutePlanRepository.list_all` |
| `GET` | `/route-plans/{route_plan_id}` | Supervisor or assigned worker | Repository `get` |
| `POST` | `/route-plans/{route_plan_id}/approve` | Supervisor | `RoutePlanningService.approve_route` |

Route generation must check vehicle capacity, travel distance, and operational constraints. Approval is human-controlled; the API does not dispatch a vehicle.

### Verify: cleanup evidence

| Method | Route | Auth | Service method |
| --- | --- | --- | --- |
| `POST` | `/incidents/{incident_id}/verification-evidence` | Assigned worker | `VerificationService.submit_evidence` |
| `GET` | `/incidents/{incident_id}/verification` | Authenticated | `VerificationService.latest_verification` |
| `POST` | `/verification/{record_id}/review` | Supervisor | `VerificationService.review_evidence` |

The evidence request is multipart and must contain an after-cleanup image. Clear cases may be verified automatically; uncertain cases must remain reviewable by a supervisor.

### Learn: audit and evaluation

| Method | Route | Auth | Service method |
| --- | --- | --- | --- |
| `GET` | `/audit/{entity_type}/{entity_id}` | Supervisor or admin | `AuditService.history` |
| `GET` | `/audit/actors/{actor_id}` | Admin | `AuditService.actor_history` |
| `POST` | `/evaluations` | Admin or evaluator | `EvaluationService.run_evaluation` |
| `GET` | `/evaluations/{run_id}` | Authenticated evaluator | `EvaluationService.get_run` |
| `GET` | `/evaluations/{run_id}/comparison` | Authenticated evaluator | `EvaluationService.compare_with_baseline` |

### Chandigarh pilot and scale readiness

| Method | Route | Auth | Service method |
| --- | --- | --- | --- |
| `POST` | `/pilots` | Admin | `PilotService.start_pilot` |
| `POST` | `/pilots/{pilot_id}/metrics` | Admin or evaluator | `PilotService.collect_metrics` |
| `POST` | `/pilots/{pilot_id}/close` | Admin | `PilotService.close_pilot` |

Pilot routes must enforce the planned 8–12 week window and keep baseline metrics separate from observed metrics.

### Municipal and IoT integrations

| Method | Route | Auth | Service method |
| --- | --- | --- | --- |
| `POST` | `/integrations/municipal/{system_name}/work-orders/export` | Admin or supervisor | `MunicipalIntegrationService.export_work_orders` |
| `POST` | `/integrations/municipal/{system_name}/status-updates/import` | Admin or supervisor | `MunicipalIntegrationService.import_status_updates` |
| `POST` | `/integrations/iot/readings` | Device credential or admin | `IoTIntegrationService.ingest_reading` |
| `GET` | `/integrations/iot/sensors/{sensor_id}/latest` | Supervisor or admin | `IoTIntegrationService.latest_reading` |
| `POST` | `/integrations/iot/readings/{reading_id}/associate` | Supervisor or admin | `IoTIntegrationService.associate_with_incident` |

IoT is optional. The core citizen-report workflow must work when no sensor integration is configured.

## 5. Request Contracts

### Create incident

`POST /api/v1/incidents` with JSON:

```json
{
  "reporter_type": "resident",
  "description": "Waste beside the market",
  "latitude": 30.7333,
  "longitude": 76.7794,
  "occurred_at": "2026-10-22T09:30:00Z"
}
```

Response: `201 Created`

```json
{
  "id": "incident-uuid",
  "status": "pending_analysis",
  "reporter_type": "resident",
  "description": "Waste beside the market",
  "latitude": 30.7333,
  "longitude": 76.7794,
  "occurred_at": "2026-10-22T09:30:00Z"
}
```

### Upload incident media

`POST /api/v1/incidents/{incident_id}/media` with multipart fields:

- `file`: image bytes
- `captured_at`: optional ISO timestamp
- `is_after_cleanup`: optional boolean; defaults to `false`

Response: `201 Created` with `id`, `storage_key`, `content_type`, `sha256`, and `is_after_cleanup`.

### Run analysis

`POST /api/v1/incidents/{incident_id}/analysis` with JSON:

```json
{
  "provider": "gemini",
  "async": true
}
```

Response: `202 Accepted` for a worker job or `200 OK` when executed synchronously:

```json
{
  "incident_id": "incident-uuid",
  "provider": "gemini",
  "model_name": "configured-model",
  "category": "mixed_waste",
  "severity": "high",
  "confidence": 0.95,
  "extracted_details": {},
  "status": "ready_for_review"
}
```

### Build a route

`POST /api/v1/route-plans` with JSON:

```json
{
  "work_order_ids": ["work-order-uuid"],
  "vehicle_capacity": 100.0,
  "constraints": {
    "max_stops": 20,
    "service_window_start": "08:00",
    "service_window_end": "16:00"
  }
}
```

Response: `201 Created` with route distance, duration, baseline distance, capacity, constraints, and ordered stops.

## 6. Standard Responses and Errors

### Success statuses

| Status | Use |
| --- | --- |
| `200 OK` | Read, update, approval, or synchronous action. |
| `201 Created` | New incident, media, work order, route, evaluation, or pilot. |
| `202 Accepted` | Background analysis, evaluation, routing, or integration job accepted. |
| `204 No Content` | Successful deletion where no representation is returned. |

### Error body

```json
{
  "error": {
    "code": "invalid_state",
    "message": "Incident is not waiting for analysis",
    "request_id": "request-uuid",
    "details": {}
  }
}
```

### Error mapping

| Exception or condition | HTTP status |
| --- | --- |
| Invalid JSON, image, coordinates, or schema | `400 Bad Request` |
| Missing or invalid bearer token | `401 Unauthorized` |
| Role or ownership failure | `403 Forbidden` |
| Repository lookup returns no entity | `404 Not Found` |
| Duplicate email or duplicate media key | `409 Conflict` |
| Invalid workflow transition | `409 Conflict` |
| External model, routing, storage, or municipal adapter failure | `502 Bad Gateway` or retryable `202` job failure |
| Unexpected server error | `500 Internal Server Error` |

## 7. Workflow Route Sequence

1. `POST /incidents` creates a `PENDING_ANALYSIS` incident.
2. `POST /incidents/{id}/media` stores before-cleanup evidence.
3. `POST /incidents/{id}/analysis` produces structured AI output and moves the incident to `READY_FOR_REVIEW`.
4. `GET /incidents/{id}/duplicate-candidates` and `POST /incidents/{id}/duplicate-clusters` support duplicate review.
5. `POST /incidents/{id}/risk-assessments` calculates an explainable hotspot score.
6. `GET /prioritization/queue` presents a risk-ranked supervisor queue.
7. `POST /work-orders` and `/approve` create and authorize sanitation work.
8. `POST /route-plans` and `/approve` create a capacity-aware, human-approved route.
9. Worker uses `/work-orders/{id}/complete` after cleanup.
10. Worker uploads after evidence through `/incidents/{id}/verification-evidence`.
11. `POST /verification/{id}/review` resolves uncertain cases.
12. `/evaluations` and `/pilots` measure resolution, recurrence, duplicate quality, route efficiency, and verified closure.

## 8. Implementation Order

1. Add FastAPI application and dependency-injected session/service factories.
2. Implement health, user, incident, media, and error-handling routes.
3. Implement analysis worker endpoint and provider selection.
4. Implement duplicate, risk, prioritization, and work-order routes.
5. Implement route and verification routes.
6. Implement audit, evaluation, pilot, municipal, and IoT routes.
7. Add OpenAPI schemas, authentication, rate limits, request IDs, and route-level tests.

## 9. Security and Operational Requirements

- Never accept `actor_id` from the request body as the source of authorization; derive it from authentication.
- Enforce role and ownership checks before calling the service.
- Validate and limit image size, content type, and upload count.
- Do not return raw model responses to reporters; expose normalized analysis and confidence according to role.
- Redact secrets, access tokens, and private storage URLs from audit details and logs.
- Apply rate limits to report creation, image uploads, AI analysis, and integration endpoints.
- Use idempotency keys for incident creation, analysis jobs, route generation, and municipal exports.
- Keep external calls outside database transactions where possible; persist only validated adapter results.
- Add OpenAPI contract tests for every route before pilot deployment.