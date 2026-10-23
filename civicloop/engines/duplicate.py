from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from civicloop.embeddings import TextEmbedder, text_similarity
from civicloop.engines.common import as_utc, haversine_km, jaccard_text


@dataclass(frozen=True)
class DuplicateEngineConfig:
    version: str = "duplicate-embed-1"
    fallback_version: str = "duplicate-baseline-1"
    radius_km: float = 0.25
    time_window_hours: float = 24.0
    threshold: float = 0.65
    candidate_limit: int = 50
    distance_weight: float = 0.35
    time_weight: float = 0.25
    text_weight: float = 0.25
    category_weight: float = 0.15


@dataclass(frozen=True)
class DuplicateMatch:
    incident_id: str
    similarity_score: float
    factors: dict[str, float]
    engine_version: str
    text_method: str = "word-overlap"


class DuplicateEngine:
    def __init__(self, config: DuplicateEngineConfig | None = None, embedder: TextEmbedder | None = None) -> None:
        self.config = config or DuplicateEngineConfig()
        self.embedder = embedder
        if self.config.radius_km <= 0 or self.config.time_window_hours <= 0:
            raise ValueError("Duplicate radius and time window must be positive")
        if not 0 <= self.config.threshold <= 1:
            raise ValueError("Duplicate threshold must be between 0 and 1")

    def compare(self, source: Any, candidate: Any, source_analysis: Any = None, candidate_analysis: Any = None) -> DuplicateMatch | None:
        distance = haversine_km((source.latitude, source.longitude), (candidate.latitude, candidate.longitude))
        time_difference = abs((as_utc(source.occurred_at) - as_utc(candidate.occurred_at)).total_seconds()) / 3600
        if distance > self.config.radius_km or time_difference > self.config.time_window_hours:
            return None
        text_score, text_method = self._text_similarity(source.description, candidate.description)
        factors = {
            "distance": max(0.0, 1 - distance / self.config.radius_km),
            "time": max(0.0, 1 - time_difference / self.config.time_window_hours),
            "text": text_score,
            "category": 1.0 if source_analysis and candidate_analysis and source_analysis.category == candidate_analysis.category else 0.0,
        }
        score = (
            self.config.distance_weight * factors["distance"]
            + self.config.time_weight * factors["time"]
            + self.config.text_weight * factors["text"]
            + self.config.category_weight * factors["category"]
        )
        if score < self.config.threshold:
            return None
        version = self.config.version if text_method == "embedding" else self.config.fallback_version
        return DuplicateMatch(str(candidate.id), score, factors, version, text_method)

    def _text_similarity(self, left: str, right: str) -> tuple[float, str]:
        """Semantic similarity when an embedder is loaded, word overlap otherwise."""
        if self.embedder is not None:
            try:
                return text_similarity(self.embedder, left, right), "embedding"
            except Exception:  # a model hiccup must never break duplicate checks
                pass
        return jaccard_text(left, right), "word-overlap"

    def find(self, source: Any, candidates: list[Any], source_analysis: Any = None, analyses: dict[str, Any] | None = None) -> list[DuplicateMatch]:
        analyses = analyses or {}
        matches = [
            match
            for candidate in sorted(candidates, key=lambda item: str(item.id))
            if str(candidate.id) != str(source.id)
            for match in [self.compare(source, candidate, source_analysis, analyses.get(str(candidate.id)))]
            if match is not None
        ]
        return sorted(matches, key=lambda item: (-item.similarity_score, item.incident_id))[: self.config.candidate_limit]