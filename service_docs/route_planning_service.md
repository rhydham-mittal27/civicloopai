# RoutePlanningService

## Repositories

- `RoutePlanRepository`: planned `add`, `get`, `list_for_date`, `add_stop`
- `WorkOrderRepository`: `list_by_status`, `get`
- `IncidentRepository`: `get`
- `UserRepository`: `get`
- `AuditEventRepository`: planned `add`

## Functions

### `build_route(work_order_ids, vehicle_capacity, constraints, actor_id)`

```text
require actor is supervisor
orders = [WorkOrderRepository.get(id) for id in work_order_ids]
require every order exists and status == APPROVED
stops = [IncidentRepository.get(order.incident_id) for order in orders]
require sum(order.estimated_volume) <= vehicle_capacity
route = RoutingAdapter.plan(stops, vehicle_capacity, constraints)
baseline = RoutingAdapter.baseline(stops)
plan = RoutePlan(vehicle_capacity, route.distance, route.duration,
                 baseline.distance, constraints)
RoutePlanRepository.add(plan)
for position, order in enumerate(orders):
    RoutePlanRepository.add_stop(plan.id, position, order.id, order.estimated_volume)
AuditEventRepository.add(actor_id, "route_plan", plan.id, "generated", {})
return plan
```

### `approve_route(route_plan_id, supervisor_id)`

```text
plan = RoutePlanRepository.get(route_plan_id)
require plan exists and supervisor role
RoutePlanRepository.approve(route_plan_id, supervisor_id)
AuditEventRepository.add(supervisor_id, "route_plan", route_plan_id, "approved", {})
return plan
```

No vehicle dispatch is performed by this service.