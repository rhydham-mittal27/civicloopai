from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from queue import Empty, PriorityQueue
from typing import Any, Callable, Mapping, Protocol

from sqlalchemy.orm import Session, sessionmaker

from civicloop.models import Job, JobStatus
from civicloop.repositories import JobRepository
from civicloop.tenancy import bind_tenant


class JobType(StrEnum):
    ANALYZE_INCIDENT = "analyze_incident"
    DETECT_DUPLICATES = "detect_duplicates"
    CALCULATE_HOTSPOT_RISK = "calculate_hotspot_risk"
    GENERATE_ROUTE = "generate_route"
    EVALUATE_DATASET = "evaluate_dataset"
    PILOT_METRICS = "pilot_metrics"
    MUNICIPAL_EXPORT = "municipal_export"
    MUNICIPAL_IMPORT = "municipal_import"
    SENSOR_INGEST = "sensor_ingest"
    STORAGE_CLEANUP = "storage_cleanup"


class JobError(RuntimeError):
    """Base queue-processing error."""


class RetryableJobError(JobError):
    pass


class PermanentJobError(JobError):
    pass


@dataclass(frozen=True)
class JobDelivery:
    job_id: str
    priority: str
    delivery_id: str


class JobQueue(Protocol):
    def enqueue(self, job_id: str, priority: str = "normal") -> None: ...

    def dequeue(self) -> JobDelivery | None: ...

    def acknowledge(self, delivery: JobDelivery) -> None: ...

    def retry(self, delivery: JobDelivery, delay_seconds: int) -> None: ...

    def dead_letter(self, delivery: JobDelivery, reason: str) -> None: ...


class InMemoryJobQueue:
    """Deterministic queue for local development and tests."""

    _priority = {"high": 0, "normal": 1, "low": 2}

    def __init__(self) -> None:
        self._queue: PriorityQueue[tuple[int, int, JobDelivery]] = PriorityQueue()
        self._sequence = 0
        self.dead_letters: list[tuple[JobDelivery, str]] = []

    def enqueue(self, job_id: str, priority: str = "normal") -> None:
        self._sequence += 1
        delivery = JobDelivery(
            job_id=job_id, priority=priority, delivery_id=str(uuid.uuid4())
        )
        self._queue.put((self._priority.get(priority, 1), self._sequence, delivery))

    def dequeue(self) -> JobDelivery | None:
        try:
            return self._queue.get_nowait()[2]
        except Empty:
            return None

    def acknowledge(self, delivery: JobDelivery) -> None:
        return None

    def retry(self, delivery: JobDelivery, delay_seconds: int) -> None:
        if delay_seconds > 0:
            time.sleep(delay_seconds)
        self.enqueue(delivery.job_id, delivery.priority)

    def dead_letter(self, delivery: JobDelivery, reason: str) -> None:
        self.dead_letters.append((delivery, reason))

    def depth(self) -> int:
        return self._queue.qsize()


class RedisJobQueue:
    """Redis list-backed queue; redis-py is imported only when this backend is used."""

    def __init__(self, url: str, prefix: str = "civicloop") -> None:
        try:
            import redis
        except ImportError as error:
            raise JobError("Install the queue extra to use RedisJobQueue") from error
        self.client = redis.Redis.from_url(url, decode_responses=True)
        self.prefix = prefix

    def _key(self, priority: str) -> str:
        return f"{self.prefix}:jobs:{priority}"

    def enqueue(self, job_id: str, priority: str = "normal") -> None:
        self.client.rpush(self._key(priority), job_id)

    def dequeue(self) -> JobDelivery | None:
        for priority in ("high", "normal", "low"):
            job_id = self.client.lpop(self._key(priority))
            if job_id is not None:
                if isinstance(job_id, bytes):
                    job_id = job_id.decode("utf-8")
                else:
                    job_id = str(job_id)
                return JobDelivery(
                    job_id=job_id, priority=priority, delivery_id=str(uuid.uuid4())
                )
        return None

    def acknowledge(self, delivery: JobDelivery) -> None:
        return None

    def retry(self, delivery: JobDelivery, delay_seconds: int) -> None:
        self.enqueue(delivery.job_id, delivery.priority)

    def dead_letter(self, delivery: JobDelivery, reason: str) -> None:
        self.client.rpush(
            f"{self.prefix}:dead-letter",
            json.dumps({"job_id": delivery.job_id, "reason": reason}),
        )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def retry_delay(
    attempt_count: int, base_seconds: int = 2, max_seconds: int = 300
) -> int:
    return min(max_seconds, base_seconds * (2 ** max(0, attempt_count - 1)))


def validate_job_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise PermanentJobError("Job payload must be an object")
    try:
        encoded = json.dumps(dict(payload))
    except (TypeError, ValueError) as error:
        raise PermanentJobError("Job payload must be JSON serializable") from error
    if len(encoded.encode("utf-8")) > 256_000:
        raise PermanentJobError("Job payload exceeds the maximum size")
    return dict(payload)


class JobDispatcher:
    def __init__(self, session_factory: sessionmaker[Session], queue: JobQueue) -> None:
        self.session_factory = session_factory
        self.queue = queue

    def dispatch(
        self,
        job_type: JobType | str,
        payload: Mapping[str, Any],
        idempotency_key: str,
        *,
        created_by: str | None = None,
        priority: str = "normal",
        max_attempts: int = 3,
        tenant_id: str | None = None,
    ) -> Job:
        if not idempotency_key.strip():
            raise ValueError("idempotency_key is required")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        normalized_payload = validate_job_payload(payload)
        normalized_type = (
            job_type.value if isinstance(job_type, JobType) else str(job_type)
        )
        from sqlalchemy.exc import IntegrityError

        with self.session_factory() as session:
            repository = JobRepository(session)
            existing = repository.get_by_idempotency_key(idempotency_key)
            if existing is not None:
                return existing
            try:
                job = repository.add(
                    Job(
                        job_type=normalized_type,
                        payload=normalized_payload,
                        idempotency_key=idempotency_key,
                        created_by=created_by,
                        max_attempts=max_attempts,
                        tenant_id=tenant_id,
                    )
                )
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = repository.get_by_idempotency_key(idempotency_key)
                if existing is not None:
                    return existing
                raise
        try:
            self.queue.enqueue(job.id, priority)
        except Exception:
            # The durable queued row remains recoverable by a republisher.
            raise
        return job

    def cancel(self, job_id: str, tenant_id: str | None = None) -> Job:
        with self.session_factory() as session:
            bind_tenant(session, tenant_id)
            repository = JobRepository(session)
            job = repository.get(job_id)
            if job is None:
                raise LookupError(f"Job not found: {job_id}")
            if job.status not in {
                JobStatus.QUEUED,
                JobStatus.FAILED,
                JobStatus.DEAD_LETTER,
            }:
                raise ValueError("Only queued or failed jobs can be cancelled")
            repository.cancel(job)
            session.commit()
            return job

    def retry(self, job_id: str, priority: str = "normal", tenant_id: str | None = None) -> Job:
        with self.session_factory() as session:
            bind_tenant(session, tenant_id)
            repository = JobRepository(session)
            job = repository.get(job_id)
            if job is None:
                raise LookupError(f"Job not found: {job_id}")
            if job.status not in {JobStatus.FAILED, JobStatus.DEAD_LETTER}:
                raise ValueError("Only failed jobs can be retried")
            job.status = JobStatus.QUEUED
            job.completed_at = None
            job.last_error_code = None
            job.last_error_message = None
            repository.update(job)
            session.commit()
        self.queue.enqueue(job_id, priority)
        return job


JobHandler = Callable[[dict[str, Any]], dict[str, Any] | None]
HandlerFactory = Callable[[Session], Mapping[str, JobHandler]]


class JobWorker:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        queue: JobQueue,
        handler_factory: HandlerFactory,
    ) -> None:
        self.session_factory = session_factory
        self.queue = queue
        self.handler_factory = handler_factory

    def run_once(self) -> bool:
        delivery = self.queue.dequeue()
        if delivery is None:
            return False
        with self.session_factory() as session:
            repository = JobRepository(session)
            job = repository.get(delivery.job_id)
            if job is None or job.status in {
                JobStatus.SUCCEEDED,
                JobStatus.CANCELLED,
                JobStatus.DEAD_LETTER,
            }:
                self.queue.acknowledge(delivery)
                return True
            current_time = utc_now()
            if job.available_at and as_utc(job.available_at) > current_time:
                self.queue.retry(
                    delivery,
                    max(
                        0,
                        int((as_utc(job.available_at) - current_time).total_seconds()),
                    ),
                )
                return True
            repository.mark_running(job, utc_now())
            session.commit()
            # everything the handler reads or writes belongs to the job's own city
            bind_tenant(session, job.tenant_id)
            try:
                handler = self.handler_factory(session).get(job.job_type)
                if handler is None:
                    raise PermanentJobError(f"No handler registered for {job.job_type}")
                result = handler(validate_job_payload(job.payload)) or {}
                repository.mark_succeeded(job, result, utc_now())
                session.commit()
                self.queue.acknowledge(delivery)
                return True
            except PermanentJobError as error:
                session.rollback()
                repository.mark_dead_letter(
                    job, utc_now(), "permanent_error", str(error)
                )
                session.commit()
                self.queue.dead_letter(delivery, str(error))
                return True
            except Exception as error:
                session.rollback()
                if job.attempt_count >= job.max_attempts:
                    repository.mark_dead_letter(
                        job, utc_now(), "max_attempts_exceeded", str(error)
                    )
                    session.commit()
                    self.queue.dead_letter(delivery, str(error))
                else:
                    delay = retry_delay(job.attempt_count)
                    repository.mark_retryable(
                        job,
                        utc_now() + timedelta(seconds=delay),
                        "retryable_error",
                        str(error),
                    )
                    session.commit()
                    self.queue.retry(delivery, delay)
                return True


def create_queue_from_env() -> JobQueue:
    backend = os.getenv("CIVICLOOP_QUEUE_BACKEND", "memory").lower()
    if backend == "memory":
        return InMemoryJobQueue()
    if backend == "redis":
        return RedisJobQueue(os.environ["CIVICLOOP_REDIS_URL"])
    raise ValueError(f"Unsupported queue backend: {backend}")
