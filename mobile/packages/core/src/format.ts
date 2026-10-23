export function shortId(id: string): string {
  return id.slice(0, 8);
}

/** "12 s ago", "3 min ago", "2 h ago"... from an age in seconds. */
export function agoFromSeconds(seconds: number | null): string {
  if (seconds === null) return "never";
  if (seconds < 8) return "just now";
  if (seconds < 90) return `${Math.round(seconds)} s ago`;
  if (seconds < 5400) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 172_800) return `${Math.round(seconds / 3600)} h ago`;
  return `${Math.round(seconds / 86_400)} days ago`;
}

/** A short, friendly time for a list: "Today 14:05", "Yesterday 09:30", "12 Oct". */
export function whenLabel(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const two = (n: number) => String(n).padStart(2, "0");
  const time = `${two(date.getHours())}:${two(date.getMinutes())}`;
  const dayKey = (d: Date) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (dayKey(date) === dayKey(now)) return `Today ${time}`;
  if (dayKey(date) === dayKey(yesterday)) return `Yesterday ${time}`;
  const month = date.toLocaleString("en-GB", { month: "short" });
  return `${date.getDate()} ${month}`;
}

export function isValidPincode(value: string): boolean {
  return /^[1-9][0-9]{5}$/.test(value);
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export interface MapPoint {
  latitude: number;
  longitude: number;
}

/** Google Maps allows a start, 9 stops in between and an end, so a long route is opened in legs of 10. */
export const MAPS_LEG = 10;

/**
 * A Google Maps directions link through the stops in order, starting from where the phone is now.
 * Opening it gives live turn-by-turn navigation. Pass only the stops still to do.
 */
export function mapsRouteUrl(stops: MapPoint[]): string | null {
  const leg = stops.slice(0, MAPS_LEG);
  if (leg.length === 0) return null;
  const at = (p: MapPoint) => `${p.latitude},${p.longitude}`;
  const last = leg[leg.length - 1]!;
  const params = [`api=1`, `travelmode=driving`, `destination=${at(last)}`];
  if (leg.length > 1) params.push(`waypoints=${leg.slice(0, -1).map(at).join("%7C")}`);
  return `https://www.google.com/maps/dir/?${params.join("&")}`;
}
