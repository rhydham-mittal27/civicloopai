from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from civicloop.ml import ModelMetadata, ModelRunner


@dataclass(frozen=True)
class EvaluationSample:
    sample_id: str
    features: dict[str, Any]
    expected_category: str | None = None
    expected_duplicate: bool | None = None
    expected_recurrence: bool | None = None


@dataclass(frozen=True)
class EvaluationReport:
    dataset_version: str
    model: ModelMetadata
    sample_count: int
    metrics: dict[str, float]
    predictions: list[dict[str, Any]] = field(default_factory=list)


class EvaluationPipeline:
    def run(self, dataset_version: str, samples: Iterable[EvaluationSample], model: ModelMetadata, runner: ModelRunner, top_k: int = 5) -> EvaluationReport:
        ordered_samples = sorted(samples, key=lambda sample: sample.sample_id)
        predictions: list[dict[str, Any]] = []
        for sample in ordered_samples:
            prediction = runner.predict(sample.features)
            if not isinstance(prediction, dict):
                raise ValueError(f"Prediction for {sample.sample_id} must be an object")
            predictions.append({"sample_id": sample.sample_id, "prediction": prediction, "expected_category": sample.expected_category, "expected_duplicate": sample.expected_duplicate, "expected_recurrence": sample.expected_recurrence})
        metrics = self._metrics(predictions, top_k)
        return EvaluationReport(dataset_version, model, len(ordered_samples), metrics, predictions)

    @staticmethod
    def _metrics(predictions: list[dict[str, Any]], top_k: int) -> dict[str, float]:
        category_rows = [row for row in predictions if row["expected_category"] is not None]
        category_accuracy = sum(row["prediction"].get("category") == row["expected_category"] for row in category_rows) / len(category_rows) if category_rows else 0.0
        duplicate_rows = [row for row in predictions if row["expected_duplicate"] is not None]
        duplicate_tp = sum(row["expected_duplicate"] is True and row["prediction"].get("is_duplicate") is True for row in duplicate_rows)
        duplicate_fp = sum(row["expected_duplicate"] is False and row["prediction"].get("is_duplicate") is True for row in duplicate_rows)
        duplicate_fn = sum(row["expected_duplicate"] is True and row["prediction"].get("is_duplicate") is not True for row in duplicate_rows)
        duplicate_precision = duplicate_tp / (duplicate_tp + duplicate_fp) if duplicate_tp + duplicate_fp else 0.0
        duplicate_recall = duplicate_tp / (duplicate_tp + duplicate_fn) if duplicate_tp + duplicate_fn else 0.0
        ranked = sorted((row for row in predictions if row["expected_recurrence"] is not None), key=lambda row: (-float(row["prediction"].get("risk_score", 0)), row["sample_id"]))[:top_k]
        risk_precision = sum(row["expected_recurrence"] is True for row in ranked) / len(ranked) if ranked else 0.0
        return {"category_accuracy": float(category_accuracy), "duplicate_precision": float(duplicate_precision), "duplicate_recall": float(duplicate_recall), "risk_precision_at_k": float(risk_precision)}