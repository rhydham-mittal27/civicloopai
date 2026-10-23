# Background Worker and Job Queue Plan

## 1. Goal

Add asynchronous processing for CivicLoopAI operations that may be slow, expensive, retryable, or dependent on external systems:

```text
API request -> enqueue job -> worker executes service -> persist result -> audit event
```

The API must remain responsive while AI analysis, duplicate detection, hotspot scoring, route planning, evaluation, and integrations run in the background.

## 2. Current State

The project currently has:

- SQLAlchemy models and repositories
- Application services under `civicloop/services`
- Gemini and open-weight AI adapters
- Object-storage adapters
- API route documentation in `route_plan.md`
- No queue, worker process, job model, job repository, or job status API yet

## 3. Recommended Architecture

Use a provider-neutral job interface with Redis as the production broker and a synchronous/in-memory backend for tests and local development.

### Components

1. **Job submission layer**
   - Services or API routes create a job request.
   - Validate payload and idempotency key.
   - Enqueue only after the request transaction has committed.

2. **Broker**
   - Redis-backed queue for local, pilot, and production deployment.
   - Separate queues for priority and workload type.

3. **Worker process**
   - Long-running Python process.
   - Claims jobs, creates a fresh database session, calls the relevant service, and commits or rolls back.
   - Does not share SQLAlchemy sessions with the API process.

4. **Job persistence**
   - Store job identity, type, status, attempts, timestamps, idempotency key, error details, and result reference in SQL.
   - Redis is a delivery mechanism, not the permanent audit record.

5. **Job status API**
   - Allow clients to poll status without exposing internal exception details or secrets.

## 4. Job Types

| Job type | Trigger | Service called | Priority | Retry policy |
| --- | --- | --- | --- | --- |
| `analyze_incident` | New report with media | `AnalysisService.analyze_incident` | High | Retry provider timeouts; do not retry invalid model output indefinitely. |
| `detect_duplicates` | Analysis completed or new nearby report | `DuplicateDetectionService` | Normal | Retry transient similarity-provider failures. |
| `calculate_hotspot_risk` | Analysis or historical data changed | `HotspotRiskService.calculate_risk` | Normal | Retry database/provider transient failures. |
| `generate_route` | Supervisor requests route | `RoutePlanningService.build_route` | High | Retry routing-provider failures; preserve approval state. |
| `evaluate_dataset` | Evaluator starts a run | `EvaluationService.run_evaluation` | Low | Retry dataset/storage failures; keep partial output out of final result. |
| `pilot_metrics` | Scheduled pilot measurement | `PilotService.collect_metrics` | Low | Retry data-read failures. |
| `municipal_export` | Supervisor/admin exports work | `MunicipalIntegrationService.export_work_orders` | High | Retry network failures with idempotency. |
| `municipal_import` | Scheduled or webhook-triggered sync | `MunicipalIntegrationService.import_status_updates` | Normal | Retry network failures; reconcile unknown records. |
| `sensor_ingest` | IoT event or batch | `IoTIntegrationService.ingest_reading` | Normal | Short retry window; reject malformed sensor payloads. |
| `storage_cleanup` | Failed upload/delete or scheduled scan | Object-storage adapter | Low | Retry provider failures and alert on exhausted attempts. |

## 5. Job Data Model

Add a `jobs` table and `JobRepository` with fields similar to:

- `id`: UUID primary key
- `job_type`: stable type string
- `status`: `queued`, `running`, `succeeded`, `failed`, `dead_letter`, `cancelled`
- `payload`: validated JSON without secrets or raw image bytes
- `result`: small JSON summary or reference to the affected entity
- `idempotency_key`: unique per logical operation
- `attempt_count`
- `max_attempts`
- `available_at`
- `started_at`
- `completed_at`
- `last_error_code`
- `last_error_message`
- `created_by`
- `created_at` and `updated_at`

Large images and model responses must remain in object storage or the existing analysis tables, not in the job payload.

## 6. Queue Contracts

### `JobQueue` interface

```python
class JobQueue(Protocol):
    def enqueue(self, job_id: str, job_type: str, priority: str = "normal") -> None: ...
    def acknowledge(self, delivery_id: str) -> None: ...
    def retry(self, delivery_id: str, delay_seconds: int) -> None: ...
    def dead_letter(self, delivery_id: str, reason: str) -> None: ...
```

### `JobDispatcher`

```text
validate job type and payload
check JobRepository for idempotency_key
if an active/succeeded job exists:
    return existing job
create queued Job through JobRepository.add
commit job record
publish job ID to JobQueue
return job status
```

If broker publishing fails after the database commit, a recovery poller must republish queued jobs. Do not mark the job as running before the broker has delivered it.

## 7. Worker Execution Flow

```text
claim delivery from queue
open fresh SQLAlchemy session
load job through JobRepository.get
if job is already succeeded/cancelled:
    acknowledge and stop
mark job running and increment attempt count
validate stored payload using the job schema
resolve service and adapter dependencies
call service method
commit service changes and mark job succeeded
acknowledge queue delivery
on retryable failure:
    rollback
    mark job queued with next available_at
    retry delivery with backoff
on permanent failure or max attempts:
    rollback service changes
    mark job dead_letter
    acknowledge queue delivery
```

Every worker execution must have a request/job correlation ID in logs and audit metadata.

## 8. Retry and Idempotency Rules

### Retryable failures

- Network timeout
- Rate limit
- Temporary provider outage
- Redis or database connection reset
- Object-storage eventual consistency error

### Permanent failures

- Invalid payload
- Missing incident, work order, or asset
- Unauthorized actor
- Invalid workflow state
- Schema-invalid model response after bounded retries
- Unsupported provider or job type

Use exponential backoff with jitter, for example:

```text
delay = min(max_delay, base_delay * 2 ** attempt_count) + random_jitter
```

Every externally visible operation must include an idempotency key. Reprocessing a job must not:

- Create duplicate analysis results for the same attempt
- Create duplicate work orders
- Create duplicate route plans
- Import the same municipal status update twice
- Create duplicate sensor readings for the same event ID

## 9. Queue Separation

Start with these logical queues:

- `civicloop.high`: analysis and supervisor-requested route jobs
- `civicloop.normal`: duplicate, risk, municipal, and IoT jobs
- `civicloop.low`: evaluation, pilot metrics, and cleanup jobs

Workers may scale independently by queue. High-priority jobs must not be blocked behind a large evaluation run.

## 10. API Integration

Long-running API routes from `route_plan.md` should return `202 Accepted`:

```json
{
  "job_id": "job-uuid",
  "status": "queued",
  "job_type": "analyze_incident",
  "status_url": "/api/v1/jobs/job-uuid"
}
```

Add these routes:

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/jobs/{job_id}` | Return status and safe result summary. |
| `POST` | `/api/v1/jobs/{job_id}/cancel` | Cancel queued jobs when policy allows. |
| `POST` | `/api/v1/jobs/{job_id}/retry` | Admin retry for failed/dead-letter jobs. |

Job status must not expose stack traces, provider tokens, raw prompts, or private image data.

## 11. Scheduling

Add scheduled jobs for:

- Recalculating hotspot scores
- Pilot metric snapshots
- Evaluation runs
- Municipal status imports
- Storage orphan cleanup
- Dead-letter review alerts

Scheduling must create normal persisted jobs, not execute business logic directly inside a scheduler callback.

## 12. Observability

Record metrics for:

- Queue depth by queue
- Job wait time
- Job execution duration
- Success, retry, and dead-letter counts
- Attempts per job type
- External provider latency and error rates
- AI token usage/cost when available
- Storage upload and cleanup failures

Log structured fields:

- `job_id`
- `job_type`
- `attempt`
- `queue`
- `entity_id`
- `provider`
- `duration_ms`
- `outcome`

Never log credentials, signed URLs, raw image bytes, or unredacted model prompts containing personal data.

## 13. Security

- Workers use a dedicated service identity with least-privilege database and storage access.
- API users cannot submit arbitrary job types or service names.
- Validate every job payload before enqueueing and again before execution.
- Do not accept an actor identity from the job payload for authorization; persist the authenticated creator and resolve permissions server-side.
- Restrict job status visibility to the creator, relevant supervisor scope, or admin.
- Protect Redis with authentication, private networking, and TLS where required.
- Encrypt sensitive job data and set retention limits.

## 14. Testing Plan

### Unit tests

- Job payload validation
- Idempotency-key reuse
- Retryable versus permanent error classification
- Backoff calculation
- Queue adapter acknowledge/retry/dead-letter behavior

### Integration tests

- Enqueue persists a job and publishes its ID.
- Worker claims a job with a fresh database session.
- Successful analysis updates incident and job status atomically.
- Failed service call rolls back domain changes.
- Exhausted retries create a dead-letter job.
- Duplicate delivery does not duplicate domain records.
- Queued jobs can be recovered when publishing fails after commit.

### Operational tests

- Worker restarts during execution.
- Redis outage.
- Database outage.
- Gemini/routing timeout.
- Large evaluation backlog does not block high-priority work.

## 15. Delivery Sequence

1. Add job enums, `Job` model, `JobRepository`, and schema tests.
2. Add job payload schemas and retry classification.
3. Implement in-memory queue and synchronous worker for tests.
4. Add `JobDispatcher` and idempotency handling.
5. Connect analysis, duplicate, risk, route, evaluation, and integration job handlers.
6. Add Redis queue backend and worker command.
7. Add job status, cancellation, and retry API routes.
8. Add scheduling, metrics, dead-letter handling, and deployment configuration.

## 16. Acceptance Criteria

- API routes return a job ID for operations exceeding the synchronous latency budget.
- Every job is durably represented in SQL and delivered through a queue.
- Workers use fresh sessions and commit service results atomically with job status.
- Retryable failures use bounded backoff; permanent failures are not retried forever.
- Idempotent delivery cannot create duplicate domain records.
- Failed jobs are visible through status APIs and dead-letter reporting.
- High-priority analysis and route jobs are isolated from low-priority evaluations.
- No secrets, raw images, or stack traces appear in job payloads or status responses.
- Tests cover success, retry, failure, duplicate delivery, restart, and broker recovery paths.