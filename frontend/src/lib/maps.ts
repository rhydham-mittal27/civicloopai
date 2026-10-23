import type { RoutePlan } from "@/lib/api";

/** Google Maps takes a start, 9 stops in between and an end, so a long route opens in legs of 10. */
export const MAPS_LEG = 10;

/** A directions link through the stops still to do, in the planned order, from the device's current position. */
export function mapsRouteUrl(plan: RoutePlan): string | null {
  const todo = plan.stops.filter((s) => !s.done && !s.reassigned && !s.cancelled && s.incident).slice(0, MAPS_LEG);
  if (todo.length === 0) return null;
  const at = (s: (typeof todo)[number]) => `${s.incident!.latitude},${s.incident!.longitude}`;
  const params = ["api=1", "travelmode=driving", `destination=${at(todo[todo.length - 1])}`];
  if (todo.length > 1) params.push(`waypoints=${todo.slice(0, -1).map(at).join("%7C")}`);
  return `https://www.google.com/maps/dir/?${params.join("&")}`;
}
