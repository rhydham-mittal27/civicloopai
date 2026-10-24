from __future__ import annotations

from civicloop.models import RiskAssessment
from civicloop.engines.risk import RiskEngine
from civicloop.tenancy import session_tenant
from civicloop.risk_model import LearnedRiskEngine, RiskModelStore
from civicloop.repositories import (
    AnalysisRepository,
    AuditEventRepository,
    IncidentRepository,
    RiskAssessmentRepository,
)
from civicloop.services.common import NotFoundError, record_audit


class HotspotRiskService:
    def __init__(
        self,
        risks: RiskAssessmentRepository,
        incidents: IncidentRepository,
        analyses: AnalysisRepository,
        audit: AuditEventRepository,
        engine: RiskEngine | None = None,
    ) -> None:
        self.risks = risks
        self.incidents = incidents
        self.analyses = analyses
        self.audit = audit
        # Use the deployed model when there is one, otherwise the hand-set formula.
        loaded = None if engine else RiskModelStore.for_tenant(session_tenant(incidents.session)).load()
        self.engine = engine or (LearnedRiskEngine(loaded) if loaded else RiskEngine())

    def calculate_risk(
        self, incident_id: str, model_version: str | None = None
    ) -> RiskAssessment:
        incident = self.incidents.get(incident_id)
        if incident is None:
            raise NotFoundError(f"Incident not found: {incident_id}")
        history = list(self.incidents.list_for_location(incident.latitude, incident.longitude))
        analysis = self.analyses.latest_for_incident(incident_id)
        result = self.engine.calculate(incident, history, analysis)
        assessment = self.risks.add(
            RiskAssessment(
                incident_id=incident_id,
                score=result.score,
                confidence=result.confidence,
                factors={**result.factors, "cutoff_at": result.cutoff_at.isoformat()},
                model_version=model_version or result.engine_version,
            )
        )
        record_audit(
            self.audit, None, "incident", incident_id, "risk_scored", {"score": result.score, "engine_version": result.engine_version}
        )
        return assessment

    def rank_incidents(self, limit: int | None = None) -> list[RiskAssessment]:
        return list(self.risks.ranked(limit=limit))

    def latest_risk(self, incident_id: str) -> RiskAssessment | None:
        return self.risks.latest_for_incident(incident_id)
