"""Background job worker.

In-process: the API starts one thread when the queue is the in-memory queue.
Stand-alone: `python -m civicloop.worker` for a Redis queue shared with the API.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import timedelta
from typing import Any, Callable

from sqlalchemy.orm import Session, sessionmaker

from civicloop.ai import AnalysisAdapter
from civicloop.container import build_services
from civicloop.job_handlers import ServiceJobHandlerFactory
from civicloop.jobs import STALE_AFTER, JobQueue, JobWorker, utc_now
from civicloop.repositories import JobRepository
from civicloop.services.municipal_integration import ManualMunicipalAdapter
from civicloop.storage import ObjectStorageAdapter

logger = logging.getLogger("civicloop.worker")


def make_worker(
    session_factory: sessionmaker[Session],
    queue: JobQueue,
    storage: ObjectStorageAdapter,
    analysis_adapter_factory: Callable[[], AnalysisAdapter] | None,
) -> JobWorker:
    handlers = ServiceJobHandlerFactory(
        lambda session: build_services(session, storage),
        analysis_adapter=analysis_adapter_factory,
        municipal_adapter=ManualMunicipalAdapter,
    )
    return JobWorker(session_factory, queue, handlers)


RECOVER_EVERY_SECONDS = 60


def recover_jobs(worker: JobWorker) -> int:
    """Put jobs back in the queue that a crash left behind: ones stuck RUNNING, and ones saved but never queued.

    Safe to repeat: a job already queued, running or finished is skipped when its extra delivery arrives."""
    try:
        with worker.session_factory() as session:
            repo = JobRepository(session)
            ids = repo.reclaim_stale(utc_now() - STALE_AFTER)
            ids += [job_id for job_id in repo.queued_ids() if job_id not in ids]
            session.commit()
        for job_id in ids:
            worker.queue.enqueue(job_id)
        return len(ids)
    except Exception:
        logger.exception("job recovery failed")
        return 0


class WorkerThread:
    def __init__(self, worker: JobWorker, idle_seconds: float = 0.5) -> None:
        self.worker = worker
        self.idle_seconds = idle_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="civicloop-worker", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        next_recovery = 0.0
        while not self._stop.is_set():
            if time.monotonic() >= next_recovery:
                recover_jobs(self.worker)
                next_recovery = time.monotonic() + RECOVER_EVERY_SECONDS
            try:
                did_work = self.worker.run_once()
            except Exception:  # keep the loop alive; the job row records the failure
                logger.exception("worker iteration failed")
                did_work = False
            if not did_work:
                self._stop.wait(self.idle_seconds)


def main() -> None:  # pragma: no cover - process entry point
    from civicloop.ai import create_analysis_adapter_from_env
    from civicloop.db import create_engine, create_session_factory, init_db
    from civicloop.jobs import create_queue_from_env
    from civicloop.storage import create_storage_from_env

    engine = create_engine(os.getenv("CIVICLOOP_DATABASE_URL", "sqlite:///civicloop.db"))
    init_db(engine)
    factory: Any = create_analysis_adapter_from_env if os.getenv("CIVICLOOP_AI_PROVIDER") else None
    worker = make_worker(create_session_factory(engine), create_queue_from_env(), create_storage_from_env(), factory)
    logger.warning("civicloop worker started")
    next_recovery = 0.0
    while True:
        if time.monotonic() >= next_recovery:
            recover_jobs(worker)
            next_recovery = time.monotonic() + RECOVER_EVERY_SECONDS
        if not worker.run_once():
            time.sleep(1)


if __name__ == "__main__":  # pragma: no cover
    main()
