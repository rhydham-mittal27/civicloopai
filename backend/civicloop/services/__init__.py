"""Application services for CivicLoopAI."""

from civicloop.services.analysis import AnalysisService
from civicloop.services.audit import AuditService
from civicloop.services.duplicate_detection import DuplicateDetectionService
from civicloop.services.evaluation import EvaluationService
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

__all__ = [
    "AnalysisService",
    "AuditService",
    "DuplicateDetectionService",
    "EvaluationService",
    "HotspotRiskService",
    "IncidentService",
    "IoTIntegrationService",
    "MLService",
    "MediaAssetService",
    "MunicipalIntegrationService",
    "PilotService",
    "PrioritizationService",
    "RoutePlanningService",
    "UserService",
    "VerificationService",
    "WorkOrderService",
]