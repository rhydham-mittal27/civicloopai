# CivicLoopAI Service Map

This document defines the application-service layer for the CivicLoopAI workflow and maps each service to the repository or repositories it should use.

Services coordinate business rules and transactions. They should not contain SQLAlchemy query construction; database access belongs in repositories. External APIs such as Gemini, object storage, routing providers, and open-weight models belong behind adapters.

## Service Conventions

- Each service receives a caller-owned SQLAlchemy `Session` or repository instances bound to the same session.
- A service owns one business operation or workflow boundary.
- Services validate state transitions and permissions before changing models.
- Services create audit events for user decisions, overrides, approvals, merges, assignments, and verification outcomes.
- The API or worker layer commits the transaction after a service operation succeeds.
- External adapters return validated domain data; services persist the result through repositories.

## Service-to-Repository Map

| Service | Responsibility | Primary repository | Supporting repositories | External adapters |
| --- | --- | --- | --- | --- |
| `UserService` | Create users, look up users, activate/deactivate accounts, and enforce role requirements. | `UserRepository` | `AuditEventRepository` | Authentication provider, if added |
| `IncidentService` | Create reports, validate metadata, attach media references, update incident state, and retrieve incident details. | `IncidentRepository` | `MediaAssetRepository`, `UserRepository`, `AuditEventRepository` | Object storage |
| `MediaAssetService` | Validate image metadata, persist storage references and hashes, and link before/after evidence to incidents. | `MediaAssetRepository` | `IncidentRepository`, `AuditEventRepository` | Object-storage adapter, image validation |
| `AnalysisService` | Request multimodal analysis, validate structured output, persist model results, and move incidents to review. | `AnalysisRepository` | `IncidentRepository`, `MediaAssetRepository`, `AuditEventRepository` | `GeminiAdapter`, `OpenWeightModelAdapter` |
| `DuplicateDetectionService` | Find candidate duplicate reports, create clusters, and support supervisor confirmation or rejection. | `DuplicateClusterRepository` | `IncidentRepository`, `AnalysisRepository`, `AuditEventRepository` | Similarity or embedding adapter, if used |
| `HotspotRiskService` | Calculate recurrence and near-term accumulation risk, explain score factors, and persist versioned assessments. | `RiskAssessmentRepository` | `IncidentRepository`, `AnalysisRepository`, `DuplicateClusterRepository`, `AuditEventRepository` | Risk model or deterministic scoring engine |
| `PrioritizationService` | Build the supervisor queue, rank incidents, apply filters, and record human overrides. | `RiskAssessmentRepository` | `IncidentRepository`, `WorkOrderRepository`, `AuditEventRepository` | None required for baseline MVP |
| `WorkOrderService` | Create, approve, edit, assign, defer, complete, or cancel sanitation work orders. | `WorkOrderRepository` | `IncidentRepository`, `UserRepository`, `AuditEventRepository` | None required for baseline MVP |
| `RoutePlanningService` | Build capacity-aware collection routes, compare them with a baseline, and persist approved plans and stops. | `RoutePlanRepository` | `WorkOrderRepository`, `IncidentRepository`, `UserRepository`, `AuditEventRepository` | Routing adapter |
| `VerificationService` | Accept after-cleanup evidence, apply rule-based checks, route uncertain cases to review, and update incident closure state. | `VerificationRepository` | `MediaAssetRepository`, `IncidentRepository`, `UserRepository`, `AuditEventRepository` | Image comparison or verification adapter, if used |
| `AuditService` | Record and query an immutable history of important actions and automated decisions. | `AuditEventRepository` | None | None |
| `EvaluationService` | Run repeatable evaluation datasets, compare results with baselines, and persist metric summaries. | `EvaluationRunRepository` | `IncidentRepository`, `AnalysisRepository`, `DuplicateClusterRepository`, `RiskAssessmentRepository`, `RoutePlanRepository`, `VerificationRepository` | Dataset loader, metric calculators |
| `PilotService` | Configure a Chandigarh pilot, establish a baseline, track pilot measurements, and produce a pilot report. | `EvaluationRunRepository` | All workflow repositories as needed, especially `IncidentRepository` and `VerificationRepository` | Reporting/export adapter |
| `MunicipalIntegrationService` | Translate CivicLoop records to and from external municipal systems while preserving auditability. | Repositories for the affected aggregate | `AuditEventRepository` | Municipal-system adapter |
| `IoTIntegrationService` | Ingest optional sensor readings and associate them with locations or incidents. | A future `SensorReadingRepository` | `IncidentRepository`, `AuditEventRepository` | IoT provider adapter |

## Workflow Services

### 1. Report and Understand

`IncidentService` creates the incident and initial media record. `AnalysisService` sends the report to a configured model adapter, validates the response, stores the normalized and raw result, and moves the incident to `READY_FOR_REVIEW`.

Repositories used:

- `IncidentRepository`
- `MediaAssetRepository`
- `AnalysisRepository`
- `AuditEventRepository`

### 2. Predict and Cluster

`DuplicateDetectionService` uses incident location/time and analysis data to create candidate clusters. `HotspotRiskService` calculates a versioned, explainable score from recurrence, severity, and contextual factors.

Repositories used:

- `DuplicateClusterRepository`
- `IncidentRepository`
- `AnalysisRepository`
- `RiskAssessmentRepository`
- `AuditEventRepository`

### 3. Prioritize and Act

`PrioritizationService` reads the latest risk assessments and incidents to build the ranked supervisor queue. `WorkOrderService` turns an approved decision into an assignable work order and records any override reason.

Repositories used:

- `RiskAssessmentRepository`
- `IncidentRepository`
- `WorkOrderRepository`
- `UserRepository`
- `AuditEventRepository`

### 4. Route

`RoutePlanningService` selects approved work orders, applies vehicle capacity and operational constraints, requests a route from the routing adapter, compares it with a baseline, and stores the route only after approval.

Repositories used:

- `RoutePlanRepository`
- `WorkOrderRepository`
- `IncidentRepository`
- `UserRepository`
- `AuditEventRepository`

### 5. Verify and Learn

`VerificationService` links an after-cleanup image to the incident, runs clear-case rules, and sends uncertain cases to a supervisor. `EvaluationService` consumes stored workflow records to measure resolution time, recurrence, duplicate quality, route efficiency, and verified closure.

Repositories used:

- `VerificationRepository`
- `MediaAssetRepository`
- `IncidentRepository`
- `EvaluationRunRepository`
- `AuditEventRepository`

## Repository Status

### Existing repositories

These are currently implemented in `civicloop/repositories.py`:

- `BaseRepository`
- `UserRepository`
- `IncidentRepository`
- `AnalysisRepository`
- `RiskAssessmentRepository`
- `WorkOrderRepository`
- `VerificationRepository`

### Repositories still required

The following repositories correspond to models already present in `civicloop/models.py` but are not implemented yet:

- `MediaAssetRepository`
- `DuplicateClusterRepository`
- `RoutePlanRepository`
- `AuditEventRepository`
- `EvaluationRunRepository`

The optional IoT scope will also require:

- `SensorReadingRepository`

## Recommended Service Package Layout

```text
civicloop/
  services/
    __init__.py
    users.py
    incidents.py
    media.py
    analysis.py
    duplicates.py
    risk.py
    prioritization.py
    work_orders.py
    routing.py
    verification.py
    audit.py
    evaluation.py
    pilot.py
    integrations.py
```

## Transaction Boundaries

| Operation | Transaction boundary |
| --- | --- |
| Create incident | Incident, media reference, and audit event commit together. |
| Complete AI analysis | Analysis result, incident status, and audit event commit together. |
| Confirm duplicate cluster | Cluster membership, confirmation decision, and audit event commit together. |
| Approve work order | Work-order state, incident state, and audit event commit together. |
| Approve route | Route plan, route stops, work-order assignment, and audit event commit together. |
| Submit verification | After-cleanup media, verification record, incident state, and audit event commit together. |
| Complete evaluation | Evaluation run metrics and audit event commit together. |

External API calls should happen before the persistence transaction is committed. If an external call fails, the service should leave the existing workflow state unchanged and record a retryable failure through the worker or job system rather than partially closing the incident.

## Important Rules

- Never let a repository decide whether a supervisor is authorized; that belongs to the service layer.
- Never delete source incidents when merging duplicates; preserve the original reports and cluster membership history.
- Never mark an incident verified only because a work order is completed.
- Never persist an AI response without its provider/model identity and schema-validation result.
- Never dispatch a vehicle automatically from route generation; route approval remains human-controlled.
- Keep provider-specific Gemini, routing, open-weight, storage, municipal, and IoT code outside repositories.