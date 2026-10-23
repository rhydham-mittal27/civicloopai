"""Builds every application service for one database session."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from civicloop.repositories import (
    AnalysisRepository,
    AuditEventRepository,
    DuplicateClusterRepository,
    EvaluationRunRepository,
    IncidentRepository,
    JobRepository,
    MediaAssetRepository,
    RiskAssessmentRepository,
    RoutePlanRepository,
    SensorReadingRepository,
    UserRepository,
    VerificationRepository,
    WorkOrderRepository,
)
from civicloop.services.analysis import AnalysisService
from civicloop.services.audit import AuditService
from civicloop.services.dashboard import DashboardService
from civicloop.services.duplicate_detection import DuplicateDetectionService
from civicloop.services.evaluation import EvaluationService
from civicloop.services.fleet import FleetService
from civicloop.services.hotspot_risk import HotspotRiskService
from civicloop.services.incident import IncidentService
from civicloop.services.iot_integration import IoTIntegrationService
from civicloop.services.media_asset import MediaAssetService
from civicloop.services.ml import MLService
from civicloop.services.municipal_integration import MunicipalIntegrationService
from civicloop.services.pilot import PilotService
from civicloop.services.prioritization import PrioritizationService
from civicloop.services.route_planning import RoutePlanningService
from civicloop.services.user import UserService
from civicloop.services.verification import VerificationService
from civicloop.services.work_order import WorkOrderService
from civicloop.storage import ObjectStorageAdapter


def build_services(session: Session, storage: ObjectStorageAdapter) -> dict[str, Any]:
    users = UserRepository(session)
    incidents = IncidentRepository(session)
    assets = MediaAssetRepository(session)
    analyses = AnalysisRepository(session)
    risks = RiskAssessmentRepository(session)
    orders = WorkOrderRepository(session)
    audit = AuditEventRepository(session)
    evaluations = EvaluationRunRepository(session)
    return {
        "fleet": FleetService(session, audit),
        "users_repo": users,
        "audit_repo": audit,
        "jobs_repo": JobRepository(session),
        "orders_repo": orders,
        "incidents_repo": incidents,
        "assets_repo": assets,
        "analyses_repo": analyses,
        "risks_repo": risks,
        "evaluations_repo": evaluations,
        "readings_repo": SensorReadingRepository(session),
        "clusters_repo": DuplicateClusterRepository(session),
        "routes_repo": RoutePlanRepository(session),
        "verifications_repo": VerificationRepository(session),
        "users": UserService(users, audit),
        "incidents": IncidentService(incidents, users, audit),
        "media": MediaAssetService(assets, incidents, users, audit, storage),
        "analysis": AnalysisService(analyses, incidents, assets, audit, storage),
        "risk": HotspotRiskService(risks, incidents, analyses, audit),
        "duplicates": DuplicateDetectionService(DuplicateClusterRepository(session), incidents, analyses, users, audit),
        "priority": PrioritizationService(risks, incidents, orders, users, audit),
        "orders": WorkOrderService(orders, incidents, users, audit),
        "routes": RoutePlanningService(RoutePlanRepository(session), orders, incidents, users, audit),
        "verification": VerificationService(
            VerificationRepository(session), assets, incidents, users, audit, storage=storage, work_orders=orders
        ),
        "audit": AuditService(audit),
        "dashboard": DashboardService(session),
        "ml": MLService(session, audit, users),
        "evaluation": EvaluationService(evaluations, audit),
        "pilot": PilotService(evaluations, audit, users),
        "municipal": MunicipalIntegrationService(orders, users, audit),
        "iot": IoTIntegrationService(SensorReadingRepository(session), incidents, audit),
    }
