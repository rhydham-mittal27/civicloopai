"""Learned hotspot-risk model.

Question the model answers: given a new report, how likely is another report within 500 m in the
next 30 days? That probability is the risk score.

Honesty rules baked in:
- Features are computed from strictly earlier reports only, by the same function for training and
  for live scoring, so the model cannot peek at the future.
- "Still open" is not a feature. Only the current status is stored, so using it for past reports
  would leak the outcome.
- Validation is chronological (train on the past, test on the latest reports).
- The trained model replaces the hand-set formula only if it beats it on that held-out slice.
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from civicloop.engines.risk import RiskResult

FEATURES = (
    "reports_7d",
    "reports_30d",
    "reports_90d",
    "decayed_recency",
    "days_since_last",
    "severity",
    "has_ai_rating",
    "ai_confidence",
)
HORIZON_DAYS = 30
RADIUS_KM = 0.5
HISTORY_DAYS = 90
HALF_LIFE_DAYS = 30.0
SEVERITY = {"low": 0.2, "medium": 0.5, "high": 0.8, "critical": 1.0}
EARTH_KM = 6371.0088
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

FEATURE_LABELS = {
    "reports_7d": "Reports nearby, last 7 days",
    "reports_30d": "Reports nearby, last 30 days",
    "reports_90d": "Reports nearby, last 90 days",
    "decayed_recency": "How fresh nearby reports are",
    "days_since_last": "Days since the last nearby report",
    "severity": "AI severity rating",
    "has_ai_rating": "Has an AI rating",
    "ai_confidence": "AI confidence",
}


def to_days(moment: datetime) -> float:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return (moment - _EPOCH).total_seconds() / 86_400


def _haversine(lat: float, lon: float, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    p1, p2 = math.radians(lat), np.radians(lats)
    dphi, dlmb = p2 - p1, np.radians(lons) - math.radians(lon)
    a = np.sin(dphi / 2) ** 2 + math.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * EARTH_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def compute_features(
    lat: float,
    lon: float,
    t: float,
    severity: str | None,
    confidence: float | None,
    hist_lat: np.ndarray,
    hist_lon: np.ndarray,
    hist_t: np.ndarray,
) -> np.ndarray:
    """Feature vector for one report. Only history strictly before `t` is used."""
    age = t - hist_t
    nearby = (age > 0) & (age <= HISTORY_DAYS)
    if nearby.any():
        nearby &= _haversine(lat, lon, hist_lat, hist_lon) <= RADIUS_KM
    ages = age[nearby]
    rated = severity is not None and severity.lower() in SEVERITY
    return np.array(
        [
            float((ages <= 7).sum()),
            float((ages <= 30).sum()),
            float(len(ages)),
            float((0.5 ** (ages / HALF_LIFE_DAYS)).sum()),
            float(ages.min()) if len(ages) else float(HISTORY_DAYS),
            SEVERITY[severity.lower()] if rated else 0.2,
            1.0 if rated else 0.0,
            float(confidence) if confidence is not None else 0.5,
        ]
    )


@dataclass(frozen=True)
class TrainingRow:
    id: str
    latitude: float
    longitude: float
    occurred_at: datetime
    severity: str | None = None
    confidence: float | None = None
    synthetic: bool = False


def build_dataset(rows: Sequence[TrainingRow], now: datetime) -> dict[str, Any]:
    """Features and the 'recurred within 30 days' label for every report whose outcome is known."""
    if not rows:
        return {"X": np.zeros((0, len(FEATURES))), "y": np.zeros(0), "t": np.zeros(0), "ids": [], "synthetic": np.zeros(0)}
    lat = np.array([r.latitude for r in rows])
    lon = np.array([r.longitude for r in rows])
    t = np.array([to_days(r.occurred_at) for r in rows])
    cutoff = to_days(now) - HORIZON_DAYS
    X, y, times, ids, synth = [], [], [], [], []
    for i, row in enumerate(rows):
        if t[i] > cutoff:  # its 30-day outcome is not known yet
            continue
        ahead = t - t[i]
        future = (ahead > 0) & (ahead <= HORIZON_DAYS)
        label = bool(future.any() and (_haversine(lat[i], lon[i], lat[future], lon[future]) <= RADIUS_KM).any())
        X.append(compute_features(lat[i], lon[i], t[i], row.severity, row.confidence, lat, lon, t))
        y.append(1.0 if label else 0.0)
        times.append(t[i])
        ids.append(row.id)
        synth.append(1.0 if row.synthetic else 0.0)
    order = np.argsort(times)
    return {
        "X": np.array(X)[order] if X else np.zeros((0, len(FEATURES))),
        "y": np.array(y)[order] if y else np.zeros(0),
        "t": np.array(times)[order] if times else np.zeros(0),
        "ids": [ids[i] for i in order],
        "synthetic": np.array(synth)[order] if synth else np.zeros(0),
    }


def baseline_formula(X: np.ndarray) -> np.ndarray:
    """The hand-set formula on the same features, without the leaky 'still open' term."""
    idx = {name: i for i, name in enumerate(FEATURES)}
    recurrence = np.minimum(X[:, idx["reports_90d"]] / 10, 1.0)
    recency = np.minimum(X[:, idx["decayed_recency"]] / 5, 1.0)
    return (0.35 * recurrence + 0.25 * recency + 0.25 * X[:, idx["severity"]]) / 0.85


def _precision_at(y: np.ndarray, score: np.ndarray, fraction: float = 0.1) -> float:
    k = max(1, int(round(len(y) * fraction)))
    top = np.argsort(-score, kind="stable")[:k]
    return float(y[top].mean())


def _metrics(y: np.ndarray, score: np.ndarray) -> dict[str, float]:
    from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

    return {
        "auc": float(roc_auc_score(y, score)),
        "average_precision": float(average_precision_score(y, score)),
        "brier": float(brier_score_loss(y, np.clip(score, 0, 1))),
        "precision_at_10pct": _precision_at(y, score),
    }


def make_candidate(kind: str, seed: int = 7):
    """The two model families compared at training time."""
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    if kind == "logistic_regression":
        return make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=1.0))
    return CalibratedClassifierCV(
        HistGradientBoostingClassifier(max_depth=3, learning_rate=0.06, max_iter=150, min_samples_leaf=20, random_state=seed),
        method="sigmoid",
        cv=3,
    )


@dataclass
class TrainOutcome:
    deployed: bool
    reason: str
    metadata: dict[str, Any]
    model: Any = None


def train_risk_model(
    rows: Sequence[TrainingRow],
    *,
    now: datetime | None = None,
    min_rows: int = 200,
    min_class: int = 25,
    margin: float = 0.01,
    seed: int = 7,
) -> TrainOutcome:
    """Train logistic regression and gradient boosting, keep the better one if it beats the formula."""
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.inspection import permutation_importance
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    now = now or datetime.now(timezone.utc)
    data = build_dataset(rows, now)
    X, y = data["X"], data["y"]
    n, positives = len(y), int(y.sum()) if len(y) else 0
    meta: dict[str, Any] = {
        "trained_at": now.isoformat(),
        "rows_labelled": n,
        "rows_total": len(rows),
        "positives": positives,
        "positive_rate": round(positives / n, 4) if n else None,
        "synthetic_share": round(float(data["synthetic"].mean()), 4) if n else 0.0,
        "horizon_days": HORIZON_DAYS,
        "radius_km": RADIUS_KM,
        "feature_names": list(FEATURES),
        "min_rows": min_rows,
    }
    if n < min_rows or positives < min_class or n - positives < min_class:
        meta["status"] = "not_enough_data"
        return TrainOutcome(
            False,
            f"Only {n} reports have a known 30-day outcome ({positives} recurred). "
            f"Training needs at least {min_rows}, with {min_class}+ of each outcome. The hand-set formula stays in use.",
            meta,
        )

    split = int(n * 0.7)
    X_tr, X_va, y_tr, y_va = X[:split], X[split:], y[:split], y[split:]
    if len(set(y_tr)) < 2 or len(set(y_va)) < 2:
        meta["status"] = "not_enough_data"
        return TrainOutcome(False, "The chronological split has only one outcome in a part, so it cannot be validated.", meta)

    candidates: dict[str, dict[str, float]] = {}
    fitted = {}
    for kind in ("logistic_regression", "gradient_boosting"):
        model = make_candidate(kind, seed).fit(X_tr, y_tr)
        candidates[kind] = _metrics(y_va, model.predict_proba(X_va)[:, 1])
        fitted[kind] = model
    best = max(candidates, key=lambda k: candidates[k]["auc"])
    base = _metrics(y_va, baseline_formula(X_va))

    meta.update(
        {
            "train_rows": int(split),
            "validation_rows": int(n - split),
            "validation": "chronological: trained on the oldest 70%, tested on the newest 30%",
            "algorithm": best,
            "candidates": candidates,
            "metrics": candidates[best],
            "baseline": {"name": "hand-set formula (risk-baseline-1)", **base},
            "feature_means": [float(v) for v in X.mean(axis=0)],
        }
    )
    importance = permutation_importance(fitted[best], X_va, y_va, scoring="roc_auc", n_repeats=8, random_state=seed)
    meta["importance"] = {name: round(float(v), 4) for name, v in zip(FEATURES, importance.importances_mean)}

    gain = candidates[best]["auc"] - base["auc"]
    meta["auc_gain_vs_baseline"] = round(gain, 4)
    if gain < margin:
        meta["status"] = "kept_baseline"
        return TrainOutcome(
            False,
            f"The trained {best.replace('_', ' ')} reached AUC {candidates[best]['auc']:.3f} against {base['auc']:.3f} for the "
            f"formula on unseen reports, short of the required +{margin:.2f}. The formula stays in use.",
            meta,
            None,
        )

    final = make_candidate(best, seed).fit(X, y)  # refit on everything once validation has passed
    version = f"risk-{'gbm' if best == 'gradient_boosting' else 'logit'}-{now.strftime('%Y%m%d%H%M')}"
    meta.update({"status": "deployed", "version": version})
    return TrainOutcome(
        True,
        f"Deployed {best.replace('_', ' ')} ({version}): AUC {candidates[best]['auc']:.3f} vs {base['auc']:.3f} for the formula on unseen reports.",
        meta,
        final,
    )


# --------------------------------------------------------------------------- storage


class RiskModelStore:
    """Model files live in CIVICLOOP_MODEL_DIR (default ./var/models)."""

    def __init__(self, directory: str | os.PathLike[str] | None = None) -> None:
        self.directory = Path(directory or os.getenv("CIVICLOOP_MODEL_DIR", "./var/models"))
        self._cache: tuple[float, "LoadedModel"] | None = None
        self._lock = threading.Lock()

    @classmethod
    def for_tenant(cls, tenant_id: str | None) -> "RiskModelStore":
        """Each city trains and deploys its own model, kept in its own sub-folder."""
        base = Path(os.getenv("CIVICLOOP_MODEL_DIR", "./var/models"))
        return cls(base / tenant_id if tenant_id else base)

    @property
    def _pointer(self) -> Path:
        return self.directory / "risk-current.json"

    @property
    def _last_run(self) -> Path:
        return self.directory / "risk-last-run.json"

    def save(self, outcome: TrainOutcome) -> None:
        import joblib

        self.directory.mkdir(parents=True, exist_ok=True)
        meta = {**outcome.metadata, "deployed": outcome.deployed, "reason": outcome.reason}
        if outcome.deployed and outcome.model is not None:
            file = self.directory / f"{meta['version']}.joblib"
            joblib.dump({"model": outcome.model, "meta": meta}, file)
            self._write_atomic(self._pointer, json.dumps({"file": file.name, "meta": meta}, indent=2))
        self._write_atomic(self._last_run, json.dumps(meta, indent=2))

    @staticmethod
    def _write_atomic(path: Path, text: str) -> None:
        """Write to a temporary file and swap it in, so a reader never sees half a file."""
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)

    def load(self) -> "LoadedModel | None":
        import joblib

        try:
            stamp = self._pointer.stat().st_mtime
        except OSError:
            return None
        with self._lock:
            if self._cache and self._cache[0] == stamp:
                return self._cache[1]
            try:
                pointer = json.loads(self._pointer.read_text(encoding="utf-8"))
                blob = joblib.load(self.directory / pointer["file"])
            except Exception:
                # the heuristic score is used instead, and the log says why
                logging.getLogger("civicloop.risk").warning("risk model could not be loaded from %s; using the built-in score", self.directory, exc_info=True)
                return None
            loaded = LoadedModel(blob["model"], blob["meta"])
            self._cache = (stamp, loaded)
            return loaded

    def current_meta(self) -> dict[str, Any] | None:
        try:
            return json.loads(self._pointer.read_text(encoding="utf-8"))["meta"]
        except (OSError, ValueError, KeyError):
            return None

    def last_run_meta(self) -> dict[str, Any] | None:
        try:
            return json.loads(self._last_run.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None


@dataclass
class LoadedModel:
    model: Any
    meta: dict[str, Any]

    def probability(self, x: np.ndarray) -> float:
        return float(self.model.predict_proba(x.reshape(1, -1))[0, 1])

    def contributions(self, x: np.ndarray) -> tuple[float, dict[str, float]]:
        """Model-agnostic explanation: how far the probability moves if each input is set to its average."""
        means = np.array(self.meta["feature_means"])
        batch = np.tile(x, (len(FEATURES) + 1, 1))
        for i in range(len(FEATURES)):
            batch[i + 1, i] = means[i]
        p = self.model.predict_proba(batch)[:, 1]
        return float(p[0]), {name: float(p[0] - p[i + 1]) for i, name in enumerate(FEATURES)}


class LearnedRiskEngine:
    """Drop-in for RiskEngine that scores with the deployed model."""

    def __init__(self, loaded: LoadedModel) -> None:
        self.loaded = loaded
        self.version = loaded.meta["version"]

    def calculate(self, target: Any, history: list[Any], analysis: Any = None, cutoff_at: datetime | None = None) -> RiskResult:
        cutoff = cutoff_at or target.occurred_at
        t = to_days(cutoff)
        others = [h for h in history if str(h.id) != str(target.id)]
        h_lat = np.array([h.latitude for h in others], dtype=float)
        h_lon = np.array([h.longitude for h in others], dtype=float)
        h_t = np.array([to_days(h.occurred_at) for h in others], dtype=float)
        severity = getattr(analysis, "severity", None)
        confidence = getattr(analysis, "confidence", None)
        x = compute_features(target.latitude, target.longitude, t, severity, confidence, h_lat, h_lon, h_t)
        probability, contributions = self.loaded.contributions(x)
        idx = {name: i for i, name in enumerate(FEATURES)}
        factors: dict[str, Any] = {
            "recurrence": min(x[idx["reports_90d"]] / 10, 1.0),
            "recency": min(x[idx["decayed_recency"]] / 5, 1.0),
            "severity": float(x[idx["severity"]]),
            "_method": self.loaded.meta.get("algorithm", "model"),
            "_contributions": {k: round(v, 4) for k, v in contributions.items()},
        }
        return RiskResult(probability, None, factors, self.version, cutoff)  # type: ignore[arg-type]
