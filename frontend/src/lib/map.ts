/** Slippy-map maths shared by the dashboard, the route planner and the route view. */

export const TILE = 256;

export interface LatLon {
  lat: number;
  lon: number;
}

export interface View {
  zoom: number;
  /** World-pixel position of the map centre at this zoom level. */
  cx: number;
  cy: number;
}

/** Web-Mercator pixel position of a coordinate at a zoom level. */
export function project(lat: number, lon: number, zoom: number) {
  const scale = TILE * 2 ** zoom;
  const sin = Math.sin((lat * Math.PI) / 180);
  return { x: ((lon + 180) / 360) * scale, y: (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * scale };
}

/** The coordinate under a world-pixel position at a zoom level (inverse of `project`). */
export function unproject(x: number, y: number, zoom: number): LatLon {
  const scale = TILE * 2 ** zoom;
  const lat = (Math.atan(Math.sinh(Math.PI * (1 - (2 * y) / scale))) * 180) / Math.PI;
  return { lat, lon: (x / scale) * 360 - 180 };
}

/** The view that fits every point with some breathing room. */
export function fitView(points: LatLon[], width: number, height: number, fill = 0.78, maxZoom = 17): View {
  if (points.length === 0) {
    const c = project(30.7333, 76.7794, 12);
    return { zoom: 12, cx: c.x, cy: c.y };
  }
  for (let zoom = maxZoom; zoom >= 3; zoom--) {
    const px = points.map((p) => project(p.lat, p.lon, zoom));
    const w = Math.max(...px.map((p) => p.x)) - Math.min(...px.map((p) => p.x));
    const h = Math.max(...px.map((p) => p.y)) - Math.min(...px.map((p) => p.y));
    if (w <= width * fill && h <= height * fill) {
      return {
        zoom,
        cx: (Math.max(...px.map((p) => p.x)) + Math.min(...px.map((p) => p.x))) / 2,
        cy: (Math.max(...px.map((p) => p.y)) + Math.min(...px.map((p) => p.y))) / 2,
      };
    }
  }
  const c = project(points[0].lat, points[0].lon, 3);
  return { zoom: 3, cx: c.x, cy: c.y };
}

/** Screen position (in the SVG viewBox) of a coordinate for a view. */
export function toScreen(view: View, width: number, height: number, p: LatLon) {
  const { x, y } = project(p.lat, p.lon, view.zoom);
  return { x: x - view.cx + width / 2, y: y - view.cy + height / 2 };
}

export function tilesFor(view: View, width: number, height: number) {
  const ox = view.cx - width / 2;
  const oy = view.cy - height / 2;
  const max = 2 ** view.zoom;
  const out: { key: string; x: number; y: number; src: string }[] = [];
  for (let tx = Math.floor(ox / TILE); tx <= Math.floor((ox + width) / TILE); tx++) {
    for (let ty = Math.floor(oy / TILE); ty <= Math.floor((oy + height) / TILE); ty++) {
      if (ty < 0 || ty >= max) continue;
      const wrapped = ((tx % max) + max) % max;
      out.push({ key: `${view.zoom}/${tx}/${ty}`, x: tx * TILE - ox, y: ty * TILE - oy, src: `https://tile.openstreetmap.org/${view.zoom}/${wrapped}/${ty}.png` });
    }
  }
  return out;
}

export function zoomBy(view: View, delta: number): View {
  const zoom = Math.max(3, Math.min(18, view.zoom + delta));
  const factor = 2 ** (zoom - view.zoom);
  return { zoom, cx: view.cx * factor, cy: view.cy * factor };
}

export function panBy(view: View, dx: number, dy: number): View {
  return { ...view, cx: view.cx - dx, cy: view.cy - dy };
}
