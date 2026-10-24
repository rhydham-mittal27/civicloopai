from __future__ import annotations

from datetime import date
from typing import Any

from civicloop.models import EvaluationRun
from civicloop.repositories import AuditEventRepository, EvaluationRunRepository
from civicloop.services.common import NotFoundError, record_audit, require_user


class PilotService:
    def __init__(
        self, evaluations: EvaluationRunRepository, audit: AuditEventRepository, users
    ) -> None:
        self.evaluations = evaluations
        self.audit = audit
        self.users = users

    def start_pilot(
        self,
        name: str,
        location: str,
        start_date: date,
        end_date: date,
        baseline_version: str,
        actor_id: str,
    ) -> EvaluationRun:
        require_user(self.users, actor_id)
        duration = (end_date - start_date).days
        if duration < 56 or duration > 84:
            raise ValueError("Pilot must be between 8 and 12 weeks")
        run = self.evaluations.add(
            EvaluationRun(
                name=name,
                dataset_version=baseline_version,
                metrics={
                    "location": location,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                },
                baseline_metrics={"version": baseline_version},
            )
        )
        record_audit(
            self.audit,
            actor_id,
            "evaluation_run",
            run.id,
            "pilot_started",
            {"location": location},
        )
        return run

    def collect_metrics(self, pilot_id: str, metrics: dict[str, Any]) -> EvaluationRun:
        run = self.evaluations.get(pilot_id)
        if run is None:
            raise NotFoundError(f"Pilot not found: {pilot_id}")
        run.metrics = {**run.metrics, **metrics}
        return self.evaluations.update(run)

    def close_pilot(self, pilot_id: str, actor_id: str) -> EvaluationRun:
        run = self.evaluations.get(pilot_id)
        if run is None:
            raise NotFoundError(f"Pilot not found: {pilot_id}")
        if not run.metrics:
            raise ValueError("Pilot metrics must be collected before closure")
        record_audit(
            self.audit,
            actor_id,
            "evaluation_run",
            pilot_id,
            "pilot_closed",
            run.metrics,
        )
        return run
