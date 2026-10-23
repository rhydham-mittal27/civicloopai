from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from civicloop.engines.common import as_utc, haversine_km, time_decay


@dataclass(frozen=True)
class RiskEngineConfig:
    version: str = "risk-baseline-1"
    history_radius_km: float = 0.5
    history_window_days: int = 90
    recent_window_days: int = 30
    recurrence_weight: float = 0.35
    recency_weight: float = 0.25
    severity_weight: float = 0.25
    unresolved_weight: float = 0.15


@dataclass(frozen=True)
class RiskResult:
    score: float
    confidence: float
    factors: dict[str, float]
    engine_version: str
    cutoff_at: datetime


class RiskEngine:
    _severity = {"low": 0.2, "medium": 0.5, "high": 0.8, "critical": 1.0}
    _open_statuses = {"pending_analysis", "ready_for_review", "approved", "in_progress", "uncertain"}

    def __init__(self, config: RiskEngineConfig | None = None) -> None:
        self.config = config or RiskEngineConfig()
        if self.config.history_radius_km <= 0 or self.config.history_window_days <= 0:
            raise ValueError("Risk history limits must be positive")

    def calculate(self, target: Any, history: list[Any], analysis: Any = None, cutoff_at: datetime | None = None) -> RiskResult:
        cutoff = as_utc(cutoff_at or target.occurred_at)
        nearby = []
        for incident in history:
            age_days = (cutoff - as_utc(incident.occurred_at)).total_seconds() / 86_400
            if 0 <= age_days <= self.config.history_window_days and haversine_km((target.latitude, target.longitude), (incident.latitude, incident.longitude)) <= self.config.history_radius_km:
                nearby.append((incident, age_days))
        recurrence = min(len({str(incident.id) for incident, _ in nearby}) / 10, 1.0)
        recency = min(sum(time_decay(age, 30) for _, age in nearby) / 5, 1.0)
        severity = self._severity.get((getattr(analysis, "severity", None) or "low").lower(), 0.2)
        unresolved = sum(1 for incident, _ in nearby if getattr(incident.status, "value", incident.status) in self._open_statuses) / max(len(nearby), 1)
        factors = {"recurrence": recurrence, "recency": recency, "severity": severity, "unresolved": unresolved}
        score = min(1.0, self.config.recurrence_weight * recurrence + self.config.recency_weight * recency + self.config.severity_weight * severity + self.config.unresolved_weight * unresolved)
        available = 3 + (1 if analysis is not None else 0)
        return RiskResult(score, available / 4, factors, self.config.version, cutoff)