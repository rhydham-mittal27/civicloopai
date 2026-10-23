"""Background job worker.

In-process: the API starts one thread when the queue is the in-memory queue.
Stand-alone: `python -m civicloop.worker` for a Redis queue shared with the API.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Callable

from sqlalchemy.orm import Session, sessionmaker

from civicloop.ai import AnalysisAdapter
from civicloop.container import build_services
from civicloop.job_handlers import ServiceJobHandlerFactory
from civicloop.jobs import JobQueue, JobWorker
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
        while not self._stop.is_set():
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
    while True:
        if not worker.run_once():
            time.sleep(1)


if __name__ == "__main__":  # pragma: no cover
    main()
