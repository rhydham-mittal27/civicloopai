from __future__ import annotations

import json
import logging
import time
import uuid
from collections import Counter, defaultdict
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Iterator


request_id_context: ContextVar[str] = ContextVar("request_id", default="")


def current_request_id() -> str:
    return request_id_context.get() or "unknown"


@contextmanager
def request_context(request_id: str | None = None) -> Iterator[str]:
    token = request_id_context.set(request_id or str(uuid.uuid4()))
    try:
        yield request_id_context.get()
    finally:
        request_id_context.reset(token)


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": current_request_id(),
        }
        extra = getattr(record, "structured", None)
        if isinstance(extra, dict):
            payload["details"] = extra
        return json.dumps(payload, default=str, sort_keys=True)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


class MetricsRegistry:
    def __init__(self) -> None:
        self.counters: Counter[tuple[str, tuple[tuple[str, str], ...]]] = Counter()
        self.timings: defaultdict[tuple[str, tuple[tuple[str, str], ...]], dict[str, float]] = defaultdict(
            lambda: {"count": 0.0, "sum": 0.0, "max": 0.0}
        )

    def increment(self, name: str, value: int = 1, **labels: object) -> None:
        self.counters[(name, self._labels(labels))] += value

    def observe(self, name: str, value: float, **labels: object) -> None:
        key = (name, self._labels(labels))
        stats = self.timings[key]
        stats["count"] += 1.0
        stats["sum"] += value
        if value > stats["max"]:
            stats["max"] = value

    def snapshot(self) -> dict[str, Any]:
        return {
            "counters": {f"{name}{dict(labels)}": value for (name, labels), value in self.counters.items()},
            "timings": {f"{name}{dict(labels)}": dict(values) for (name, labels), values in self.timings.items()},
        }

    @staticmethod
    def _labels(labels: dict[str, object]) -> tuple[tuple[str, str], ...]:
        return tuple(sorted((key, str(value)) for key, value in labels.items()))


@contextmanager
def observe_operation(metrics: MetricsRegistry, logger: logging.Logger, operation: str, **labels: object) -> Iterator[None]:
    started = time.perf_counter()
    metrics.increment("operations_started", operation=operation, **labels)
    try:
        yield
    except Exception as error:
        metrics.increment("operations_failed", operation=operation, error=type(error).__name__, **labels)
        logger.error("operation_failed", extra={"structured": {"operation": operation, "error": type(error).__name__, **labels}})
        raise
    else:
        metrics.increment("operations_succeeded", operation=operation, **labels)
    finally:
        duration = time.perf_counter() - started
        metrics.observe("operation_duration_seconds", duration, operation=operation, **labels)