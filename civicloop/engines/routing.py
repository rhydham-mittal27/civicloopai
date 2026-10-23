from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from civicloop.engines.common import haversine_km

try:  # OR-Tools is an optional extra: without it the planner falls back to nearest-neighbour.
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2
except ImportError:  # pragma: no cover - exercised only when the extra is missing
    pywrapcp = None
    routing_enums_pb2 = None


def ortools_available() -> bool:
    return pywrapcp is not None


@dataclass(frozen=True)
class RouteEngineConfig:
    version: str = "route-ortools-1"
    average_speed_kmh: float = 25.0
    return_to_depot: bool = True
    solver: str = "ortools"  # "ortools" or "greedy"
    # How much sooner a high-priority stop should be reached, as a fraction of its distance cost.
    # 0 = pure shortest tour. 0.1 means a priority-100 stop's arrival distance counts 10% as much
    # as the tour length itself.
    priority_weight: float = 0.1
    time_limit_seconds: int = 2


@dataclass(frozen=True)
class RouteStopResult:
    work_order_id: str
    latitude: float
    longitude: float
    planned_volume: float
    sequence: int


@dataclass(frozen=True)
class RouteResult:
    engine_version: str
    stops: list[RouteStopResult]
    distance_km: float
    duration_minutes: float
    total_volume: float
    assumptions: dict[str, Any]
    solver: str = "greedy"
    greedy_distance_km: float = 0.0
    greedy_order: list[str] = field(default_factory=list)


class RouteEngine:
    def __init__(self, config: RouteEngineConfig | None = None) -> None:
        self.config = config or RouteEngineConfig()
        if self.config.average_speed_kmh <= 0:
            raise ValueError("Average speed must be positive")
        if self.config.priority_weight < 0:
            raise ValueError("Priority weight cannot be negative")

    def build(
        self,
        orders: list[Any],
        incidents: dict[str, Any],
        vehicle_capacity: float,
        depot: tuple[float, float] | None = None,
        constraints: dict[str, Any] | None = None,
    ) -> RouteResult:
        constraints = constraints or {}
        if vehicle_capacity <= 0:
            raise ValueError("Vehicle capacity must be positive")
        if len({str(order.id) for order in orders}) != len(orders):
            raise ValueError("Duplicate work orders are not allowed")
        total_volume = sum(order.estimated_volume or 0 for order in orders)
        if any((order.estimated_volume or 0) < 0 for order in orders) or total_volume > vehicle_capacity:
            raise ValueError("Route volume exceeds vehicle capacity or contains negative volume")
        max_minutes = constraints.get("max_duration_minutes")
        if max_minutes is not None and float(max_minutes) <= 0:
            raise ValueError("Maximum route duration must be positive")

        coords = {str(order.id): self._coordinates(order, incidents) for order in orders}
        greedy = self._greedy(orders, coords, depot)
        greedy_km = self._length(greedy, coords, depot)

        chosen, solver = greedy, "nearest-neighbour"
        if self.config.solver == "ortools" and ortools_available() and len(orders) >= 3:
            optimised = self._ortools(orders, coords, depot, greedy, max_minutes)
            if optimised is not None:
                chosen, solver = optimised, "ortools"
        distance = self._length(chosen, coords, depot)
        duration = distance / self.config.average_speed_kmh * 60
        if max_minutes is not None and duration > float(max_minutes) + 1e-6:
            raise ValueError(
                f"This route needs about {duration:.0f} min of driving, over the {float(max_minutes):.0f} min limit"
            )

        by_id = {str(order.id): order for order in orders}
        stops = [
            RouteStopResult(
                order_id,
                coords[order_id][0],
                coords[order_id][1],
                by_id[order_id].estimated_volume or 0,
                sequence,
            )
            for sequence, order_id in enumerate(chosen)
        ]
        return RouteResult(
            self.config.version,
            stops,
            distance,
            duration,
            total_volume,
            {
                "depot": depot,
                "return_to_depot": self.config.return_to_depot,
                "priority_weight": self.config.priority_weight,
                "constraints": constraints,
            },
            solver=solver,
            greedy_distance_km=greedy_km,
            greedy_order=list(greedy),
        )

    # ------------------------------------------------------------------ helpers

    def _length(self, sequence: list[str], coords: dict[str, tuple[float, float]], depot: tuple[float, float] | None) -> float:
        points = [coords[i] for i in sequence]
        distance = sum(haversine_km(a, b) for a, b in zip(points, points[1:]))
        if depot is not None and points:
            distance += haversine_km(depot, points[0])
            if self.config.return_to_depot:
                distance += haversine_km(points[-1], depot)
        return distance

    def _greedy(self, orders: list[Any], coords: dict[str, tuple[float, float]], depot: tuple[float, float] | None) -> list[str]:
        """Nearest-neighbour, highest priority first when the start is free."""
        remaining = sorted(orders, key=lambda order: (-order.priority, str(order.id)))
        if not remaining:
            return []
        current = depot or coords[str(remaining[0].id)]
        sequence: list[str] = []
        while remaining:
            nxt = min(
                remaining,
                key=lambda order: (haversine_km(current, coords[str(order.id)]), -order.priority, str(order.id)),
            )
            sequence.append(str(nxt.id))
            current = coords[str(nxt.id)]
            remaining.remove(nxt)
        return sequence

    def _ortools(
        self,
        orders: list[Any],
        coords: dict[str, tuple[float, float]],
        depot: tuple[float, float] | None,
        initial: list[str],
        max_minutes: float | None,
    ) -> list[str] | None:
        """One vehicle, shortest tour with a soft pull that brings high-priority stops forward.

        Distances are in decimetres. Node 0 is the depot, or a free dummy start when no depot is
        given (then the route is an open path starting and ending wherever is best).
        """
        ids = [str(order.id) for order in orders]
        priority = {str(order.id): max(0, min(int(order.priority), 100)) for order in orders}
        points: list[tuple[float, float] | None] = [depot] + [coords[i] for i in ids]
        n = len(points)

        def metres(a: int, b: int) -> int:
            if a == b:
                return 0
            if points[a] is None or points[b] is None:
                return 0  # the dummy start is free to leave and free to return to
            if depot is not None and not self.config.return_to_depot and b == 0:
                return 0
            return int(round(haversine_km(points[a], points[b]) * 10_000))  # decimetres

        matrix = [[metres(a, b) for b in range(n)] for a in range(n)]
        manager = pywrapcp.RoutingIndexManager(n, 1, 0)
        routing = pywrapcp.RoutingModel(manager)

        scale = 100  # arc cost is scaled so the integer priority coefficients stay fine-grained

        def arc_cost(from_index: int, to_index: int) -> int:
            return matrix[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)] * scale

        def arc_length(from_index: int, to_index: int) -> int:
            return matrix[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]

        routing.SetArcCostEvaluatorOfAllVehicles(routing.RegisterTransitCallback(arc_cost))
        horizon = 10**9
        if max_minutes is not None:
            horizon = int(self.config.average_speed_kmh * 1000 / 60 * float(max_minutes) * 10)
        routing.AddDimension(routing.RegisterTransitCallback(arc_length), 0, horizon, True, "Distance")
        distance = routing.GetDimensionOrDie("Distance")
        for node, order_id in enumerate(ids, start=1):
            coefficient = int(round(priority[order_id] * self.config.priority_weight))
            if coefficient > 0:
                distance.SetCumulVarSoftUpperBound(manager.NodeToIndex(node), 0, coefficient)

        params = pywrapcp.DefaultRoutingSearchParameters()
        params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        params.time_limit.seconds = self.config.time_limit_seconds

        index_of = {order_id: node for node, order_id in enumerate(ids, start=1)}
        routing.CloseModelWithParameters(params)
        seed = routing.ReadAssignmentFromRoutes([[index_of[i] for i in initial]], True)
        solution = routing.SolveFromAssignmentWithParameters(seed, params) if seed else routing.SolveWithParameters(params)
        if solution is None:
            return None
        sequence: list[str] = []
        index = routing.Start(0)
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            if node != 0:
                sequence.append(ids[node - 1])
            index = solution.Value(routing.NextVar(index))
        return sequence if len(sequence) == len(ids) else None

    @staticmethod
    def _coordinates(order: Any, incidents: dict[str, Any]) -> tuple[float, float]:
        incident = incidents.get(str(order.incident_id))
        if incident is None:
            raise ValueError(f"Incident not found for work order {order.id}")
        return incident.latitude, incident.longitude
