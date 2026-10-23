from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from civicloop.models import EvaluationRun
from civicloop.evaluation_pipeline import EvaluationPipeline, EvaluationSample
from civicloop.ml import ModelMetadata, ModelRunner
from civicloop.repositories import AuditEventRepository, EvaluationRunRepository
from civicloop.services.common import NotFoundError, record_audit


class EvaluationService:
    def __init__(
        self, evaluations: EvaluationRunRepository, audit: AuditEventRepository
    ) -> None:
        self.evaluations = evaluations
        self.audit = audit

    def run_evaluation(
        self,
        dataset_version: str,
        name: str,
        metric_functions: Mapping[str, Callable[[], Any]],
        baseline_metrics: Mapping[str, Any] | None = None,
    ) -> EvaluationRun:
        metrics = {
            metric_name: function()
            for metric_name, function in metric_functions.items()
        }
        run = self.evaluations.add(
            EvaluationRun(
                name=name,
                dataset_version=dataset_version,
                metrics=metrics,
                baseline_metrics=dict(baseline_metrics or {}),
            )
        )
        record_audit(
            self.audit,
            None,
            "evaluation_run",
            run.id,
            "completed",
            {"dataset": dataset_version},
        )
        return run

    def get_run(self, run_id: str) -> EvaluationRun:
        run = self.evaluations.get(run_id)
        if run is None:
            raise NotFoundError(f"Evaluation run not found: {run_id}")
        return run

    def compare_with_baseline(self, run_id: str) -> dict[str, Any]:
        run = self.get_run(run_id)
        baseline = run.baseline_metrics or {}
        return {
            key: {"value": value, "baseline": baseline.get(key)}
            for key, value in run.metrics.items()
        }

    def run_pipeline(
        self,
        dataset_version: str,
        name: str,
        samples: list[EvaluationSample],
        model: ModelMetadata,
        runner: ModelRunner,
        baseline_metrics: Mapping[str, Any] | None = None,
    ) -> EvaluationRun:
        report = EvaluationPipeline().run(dataset_version, samples, model, runner)
        run = self.evaluations.add(
            EvaluationRun(
                name=name,
                dataset_version=dataset_version,
                metrics={**report.metrics, "sample_count": report.sample_count, "model": model.version},
                baseline_metrics=dict(baseline_metrics or {}),
            )
        )
        record_audit(self.audit, None, "evaluation_run", run.id, "pipeline_completed", {"dataset": dataset_version, "model": model.version})
        return run
