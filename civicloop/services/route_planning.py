from __future__ import annotations

from typing import Any, Protocol

from civicloop.models import RoutePlan, UserRole, WorkOrderStatus
from civicloop.engines.common import haversine_km
from civicloop.engines.routing import RouteEngine
from civicloop.repositories import (
    AuditEventRepository,
    IncidentRepository,
    RoutePlanRepository,
    UserRepository,
    WorkOrderRepository,
)
from civicloop.services.common import NotFoundError, record_audit, require_user


class RoutingAdapter(Protocol):
    def plan(
        self,
        stops: list[tuple[float, float]],
        vehicle_capacity: float,
        constraints: dict[str, Any],
    ) -> dict[str, float]: ...
    def baseline(self, stops: list[tuple[float, float]]) -> dict[str, float]: ...


class RoutePlanningService:
    def __init__(
        self,
        routes: RoutePlanRepository,
        work_orders: WorkOrderRepository,
        incidents: IncidentRepository,
        users: UserRepository,
        audit: AuditEventRepository,
        engine: RouteEngine | None = None,
    ) -> None:
        self.routes = routes
        self.work_orders = work_orders
        self.incidents = incidents
        self.users = users
        self.audit = audit
        self.engine = engine or RouteEngine()

    def build_route(
        self,
        work_order_ids: list[str],
        vehicle_capacity: float,
        constraints: dict[str, Any],
        actor_id: str,
        adapter: RoutingAdapter | None = None,
        depot: tuple[float, float] | None = None,
    ) -> RoutePlan:
        require_user(self.users, actor_id, {UserRole.SUPERVISOR, UserRole.ADMIN})
        orders = [self.work_orders.get(order_id) for order_id in work_order_ids]
        if any(order is None for order in orders):
            raise NotFoundError("One or more work orders were not found")
        valid_orders = [order for order in orders if order is not None]
        if any(order.status not in {WorkOrderStatus.APPROVED, WorkOrderStatus.ASSIGNED} for order in valid_orders):
            raise ValueError("Only approved or assigned work orders can be routed")
        volume = sum(order.estimated_volume or 0 for order in valid_orders)
        if volume > vehicle_capacity:
            raise ValueError("Route exceeds vehicle capacity")
        incidents = [self.incidents.get(order.incident_id) for order in valid_orders]
        stops = [
            (incident.latitude, incident.longitude)
            for incident in incidents
            if incident is not None
        ]
        if adapter is None:
            route_result = self.engine.build(valid_orders, {str(incident.id): incident for incident in incidents if incident is not None}, vehicle_capacity, depot=depot, constraints=constraints)
            route = {"distance_km": route_result.distance_km, "duration_minutes": route_result.duration_minutes}
            # Baseline: visit the stops in the order they were selected, same depot rules.
            ordered = ([depot] if depot else []) + stops + ([depot] if depot and self.engine.config.return_to_depot else [])
            baseline = {"distance_km": sum(haversine_km(a, b) for a, b in zip(ordered, ordered[1:]))}
            engine_version = route_result.engine_version
            extra = {
                "solver": route_result.solver,
                "greedy_distance_km": route_result.greedy_distance_km,
                "greedy_order": route_result.greedy_order,
                "selection_order": [str(order.id) for order in valid_orders],
                "depot": list(depot) if depot else None,
            }
        else:
            route = adapter.plan(stops, vehicle_capacity, constraints)
            baseline = adapter.baseline(stops)
            engine_version = "routing-adapter"
            extra = {"solver": "external adapter"}
        plan = self.routes.add(
            RoutePlan(
                vehicle_capacity=vehicle_capacity,
                estimated_distance_km=route["distance_km"],
                estimated_duration_minutes=route["duration_minutes"],
                baseline_distance_km=baseline["distance_km"],
                constraints={**constraints, "engine_version": engine_version, **extra},
            )
        )
        if adapter is None:
            for stop in route_result.stops:
                self.routes.add_stop(plan.id, stop.sequence, stop.work_order_id, stop.planned_volume)
        else:
            for sequence, order in enumerate(valid_orders):
                self.routes.add_stop(plan.id, sequence, order.id, order.estimated_volume)
        record_audit(self.audit, actor_id, "route_plan", plan.id, "generated")
        return plan

    def preview_route(
        self,
        work_order_ids: list[str],
        vehicle_capacity: float,
        constraints: dict[str, Any],
        actor_id: str,
        depot: tuple[float, float] | None = None,
    ) -> dict[str, Any]:
        """Plan a route without saving it, so a supervisor can compare before committing."""
        require_user(self.users, actor_id, {UserRole.SUPERVISOR, UserRole.ADMIN})
        orders = [self.work_orders.get(order_id) for order_id in work_order_ids]
        if any(order is None for order in orders):
            raise NotFoundError("One or more work orders were not found")
        valid = [order for order in orders if order is not None]
        if any(order.status not in {WorkOrderStatus.APPROVED, WorkOrderStatus.ASSIGNED} for order in valid):
            raise ValueError("Only approved or assigned work orders can be routed")
        incidents = {str(o.incident_id): self.incidents.get(o.incident_id) for o in valid}
        result = self.engine.build(valid, {k: v for k, v in incidents.items() if v is not None}, vehicle_capacity, depot=depot, constraints=constraints)
        stops = [(incidents[str(o.incident_id)].latitude, incidents[str(o.incident_id)].longitude) for o in valid]
        ordered = ([depot] if depot else []) + stops + ([depot] if depot and self.engine.config.return_to_depot else [])
        baseline_km = sum(haversine_km(a, b) for a, b in zip(ordered, ordered[1:]))
        return {"result": result, "orders": {str(o.id): o for o in valid}, "incidents": incidents, "baseline_km": baseline_km, "selection_order": [str(o.id) for o in valid]}

    def approve_route(self, route_plan_id: str, supervisor_id: str) -> RoutePlan:
        require_user(self.users, supervisor_id, {UserRole.SUPERVISOR, UserRole.ADMIN})
        existing = self.routes.get(route_plan_id)
        if existing is not None and existing.approved_by is not None:
            raise ValueError("This route is already approved")
        plan = self.routes.approve(route_plan_id, supervisor_id)
        record_audit(self.audit, supervisor_id, "route_plan", route_plan_id, "approved")
        return plan
