from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from civicloop.ai import AnalysisAdapter
from civicloop.jobs import JobHandler, JobType, PermanentJobError
from civicloop.services.analysis import AnalysisService
from civicloop.services.duplicate_detection import DuplicateDetectionService
from civicloop.services.evaluation import EvaluationService
from civicloop.services.hotspot_risk import HotspotRiskService
from civicloop.services.iot_integration import IoTIntegrationService
from civicloop.services.municipal_integration import MunicipalIntegrationService
from civicloop.services.pilot import PilotService
from civicloop.services.route_planning import RoutePlanningService, RoutingAdapter

ServiceFactory = Callable[[Session], Mapping[str, Any]]
AIAdapterFactory = Callable[[], AnalysisAdapter]
RoutingAdapterFactory = Callable[[], RoutingAdapter]
MunicipalAdapterFactory = Callable[[], Any]
MetricFactory = Callable[[dict[str, Any]], Mapping[str, Callable[[], Any]]]


class ServiceJobHandlerFactory:
    """Build worker handlers bound to the worker's fresh SQLAlchemy session."""

    def __init__(
        self,
        services: ServiceFactory,
        *,
        analysis_adapter: AIAdapterFactory | None = None,
        routing_adapter: RoutingAdapterFactory | None = None,
        municipal_adapter: MunicipalAdapterFactory | None = None,
        metrics: MetricFactory | None = None,
    ) -> None:
        self.services = services
        self.analysis_adapter = analysis_adapter
        self.routing_adapter = routing_adapter
        self.municipal_adapter = municipal_adapter
        self.metrics = metrics

    def __call__(self, session: Session) -> Mapping[str, JobHandler]:
        service_map = self.services(session)
        handlers: dict[str, JobHandler] = {}
        if self.analysis_adapter is not None:
            handlers[JobType.ANALYZE_INCIDENT] = self._analysis_handler(
                self._service(service_map, "analysis", AnalysisService),
                service_map.get("risk"),
            )
        handlers[JobType.DETECT_DUPLICATES] = self._duplicate_handler(self._service(service_map, "duplicates", DuplicateDetectionService))
        handlers[JobType.CALCULATE_HOTSPOT_RISK] = self._risk_handler(self._service(service_map, "risk", HotspotRiskService))
        if "routes" in service_map:
            handlers[JobType.GENERATE_ROUTE] = self._route_handler(self._service(service_map, "routes", RoutePlanningService))
        if self.metrics is not None:
            handlers[JobType.EVALUATE_DATASET] = self._evaluation_handler(self._service(service_map, "evaluation", EvaluationService))
        if "pilot" in service_map:
            handlers[JobType.PILOT_METRICS] = self._pilot_handler(self._service(service_map, "pilot", PilotService))
        if self.municipal_adapter is not None and "municipal" in service_map:
            handlers[JobType.MUNICIPAL_EXPORT] = self._municipal_export_handler(self._service(service_map, "municipal", MunicipalIntegrationService))
        if "iot" in service_map:
            handlers[JobType.SENSOR_INGEST] = self._sensor_handler(self._service(service_map, "iot", IoTIntegrationService))
        return handlers

    @staticmethod
    def _service(service_map: Mapping[str, Any], name: str, service_type: type[Any]) -> Any:
        service = service_map.get(name)
        if not isinstance(service, service_type):
            raise TypeError(f"Service factory must provide {name} as {service_type.__name__}")
        return service

    def _analysis_handler(self, service: AnalysisService, risk: HotspotRiskService | None = None) -> JobHandler:
        def handle(payload: dict[str, Any]) -> dict[str, Any]:
            try:
                result = service.analyze_incident(str(payload["incident_id"]), self.analysis_adapter())
            except (KeyError, ValueError) as error:
                raise PermanentJobError(str(error)) from error
            summary = {"analysis_id": result.id, "incident_id": result.incident_id, "provider": result.provider}
            if isinstance(risk, HotspotRiskService):
                assessment = risk.calculate_risk(result.incident_id)
                summary["risk_score"] = assessment.score
            return summary

        return handle

    @staticmethod
    def _duplicate_handler(service: DuplicateDetectionService) -> JobHandler:
        def handle(payload: dict[str, Any]) -> dict[str, Any]:
            try:
                candidates = service.find_candidates(str(payload["incident_id"]), limit=int(payload.get("limit", 50)))
            except (KeyError, ValueError) as error:
                raise PermanentJobError(str(error)) from error
            return {"incident_id": str(payload["incident_id"]), "candidates": [{"incident_id": incident_id, "score": score} for incident_id, score in candidates]}

        return handle

    @staticmethod
    def _risk_handler(service: HotspotRiskService) -> JobHandler:
        def handle(payload: dict[str, Any]) -> dict[str, Any]:
            try:
                result = service.calculate_risk(str(payload["incident_id"]), payload.get("model_version"))
            except (KeyError, ValueError) as error:
                raise PermanentJobError(str(error)) from error
            return {"risk_assessment_id": result.id, "incident_id": result.incident_id, "score": result.score}

        return handle

    def _route_handler(self, service: RoutePlanningService) -> JobHandler:
        def handle(payload: dict[str, Any]) -> dict[str, Any]:
            try:
                adapter = self.routing_adapter() if self.routing_adapter is not None else None
                result = service.build_route(list(payload["work_order_ids"]), float(payload["vehicle_capacity"]), dict(payload.get("constraints", {})), str(payload["actor_id"]), adapter)
            except (KeyError, ValueError) as error:
                raise PermanentJobError(str(error)) from error
            return {"route_plan_id": result.id, "distance_km": result.estimated_distance_km}

        return handle

    def _evaluation_handler(self, service: EvaluationService) -> JobHandler:
        def handle(payload: dict[str, Any]) -> dict[str, Any]:
            try:
                result = service.run_evaluation(str(payload["dataset_version"]), str(payload.get("name", "background-evaluation")), self.metrics(payload), payload.get("baseline_metrics"))
            except (KeyError, ValueError) as error:
                raise PermanentJobError(str(error)) from error
            return {"evaluation_run_id": result.id, "metrics": result.metrics}

        return handle

    @staticmethod
    def _pilot_handler(service: PilotService) -> JobHandler:
        def handle(payload: dict[str, Any]) -> dict[str, Any]:
            result = service.collect_metrics(str(payload["pilot_id"]), dict(payload.get("metrics", {})))
            return {"pilot_id": result.id, "metrics": result.metrics}

        return handle

    def _municipal_export_handler(self, service: MunicipalIntegrationService) -> JobHandler:
        def handle(payload: dict[str, Any]) -> dict[str, Any]:
            response = service.export_work_orders(list(payload["work_order_ids"]), str(payload["system_name"]), str(payload["actor_id"]), self.municipal_adapter())
            return {"response": response}

        return handle

    @staticmethod
    def _sensor_handler(service: IoTIntegrationService) -> JobHandler:
        def handle(payload: dict[str, Any]) -> dict[str, Any]:
            try:
                reading = service.ingest_reading(str(payload["sensor_id"]), float(payload["latitude"]), float(payload["longitude"]), dict(payload["reading"]), datetime.fromisoformat(str(payload["observed_at"])))
            except (KeyError, ValueError) as error:
                raise PermanentJobError(str(error)) from error
            return {"sensor_reading_id": reading.id}

        return handle