from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from civicloop.embeddings import embedder_status
from civicloop.engines.routing import ortools_available
from civicloop.models import AnalysisResult, Incident, User, UserRole
from civicloop.repositories import AuditEventRepository
from civicloop.tenancy import session_tenant
from civicloop.risk_model import RiskModelStore, TrainingRow, train_risk_model
from civicloop.services.common import record_audit, require_user
from civicloop.synthetic import SYNTHETIC_LIKE


class MLService:
    def __init__(self, session: Session, audit: AuditEventRepository, users, store: RiskModelStore | None = None) -> None:
        self.session = session
        self.audit = audit
        self.users = users
        self.store = store or RiskModelStore.for_tenant(session_tenant(session))

    def training_rows(self) -> list[TrainingRow]:
        latest: dict[str, AnalysisResult] = {}
        for analysis in self.session.scalars(select(AnalysisResult).order_by(AnalysisResult.created_at)):
            latest[analysis.incident_id] = analysis  # later rows overwrite earlier ones
        synthetic_ids = {
            row for row in self.session.scalars(select(User.id).where(User.email.like(SYNTHETIC_LIKE)))
        }
        rows = []
        for incident in self.session.scalars(select(Incident)):
            analysis = latest.get(incident.id)
            rows.append(
                TrainingRow(
                    id=incident.id,
                    latitude=incident.latitude,
                    longitude=incident.longitude,
                    occurred_at=incident.occurred_at,
                    severity=analysis.severity if analysis else None,
                    confidence=analysis.confidence if analysis else None,
                    synthetic=incident.reporter_id in synthetic_ids,
                )
            )
        return rows

    def train_risk(self, actor_id: str) -> dict[str, Any]:
        require_user(self.users, actor_id, {UserRole.ADMIN})
        outcome = train_risk_model(self.training_rows())
        self.store.save(outcome)
        record_audit(
            self.audit,
            actor_id,
            "ml_model",
            "risk",
            "trained",
            {"deployed": outcome.deployed, "reason": outcome.reason},
        )
        return {"deployed": outcome.deployed, "reason": outcome.reason, "model": outcome.metadata}

    def status(self) -> dict[str, Any]:
        current = self.store.current_meta()
        last = self.store.last_run_meta()
        return {
            "risk": {
                "active": "model" if current else "formula",
                "current": current,
                "last_run": last,
            },
            "duplicates": embedder_status(),
            "routing": {"solver": "ortools" if ortools_available() else "nearest-neighbour"},
        }
