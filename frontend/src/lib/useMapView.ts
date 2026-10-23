"use client";

import { useMemo, useRef, useState, type RefObject } from "react";
import { fitView, panBy, project, tilesFor, zoomBy, type LatLon, type View } from "./map";

/**
 * Pan, zoom and "fit all" for an SVG map. The user's own view wins until the points being
 * fitted change, then the map re-fits.
 */
export function useMapView(points: LatLon[], width: number, height: number, svgRef: RefObject<SVGSVGElement | null>, fill = 0.78) {
  const key = points.map((p) => `${p.lat.toFixed(5)},${p.lon.toFixed(5)}`).join("|");
  const fitted = useMemo(() => fitView(points, width, height, fill), [key, width, height, fill]); // eslint-disable-line react-hooks/exhaustive-deps
  const [custom, setCustom] = useState<{ key: string; view: View } | null>(null);
  const view = custom && custom.key === key ? custom.view : fitted;
  const set = (next: View) => setCustom({ key, view: next });
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const [dragging, setDragging] = useState(false);
  const tiles = useMemo(() => tilesFor(view, width, height), [view, width, height]);

  return {
    view,
    tiles,
    dragging,
    zoomIn: () => set(zoomBy(view, 1)),
    zoomOut: () => set(zoomBy(view, -1)),
    fit: () => setCustom(null),
    centreOn: (p: LatLon, zoom = 15) => {
      const z = Math.max(view.zoom, zoom);
      const c = project(p.lat, p.lon, z);
      set({ zoom: z, cx: c.x, cy: c.y });
    },
    /** Spread these on the <svg>. */
    /** `onClick` receives the click position in viewBox units, only when the pointer did not drag. */
    handlers: (onClick?: (point: { x: number; y: number }) => void) => ({
      onPointerDown: (e: React.PointerEvent<SVGSVGElement>) => {
        if ((e.target as Element).closest(".pin")) return;
        drag.current = { x: e.clientX, y: e.clientY, moved: false };
        e.currentTarget.setPointerCapture(e.pointerId);
        setDragging(true);
      },
      onPointerMove: (e: React.PointerEvent<SVGSVGElement>) => {
        if (!drag.current) return;
        const r = width / (svgRef.current?.getBoundingClientRect().width ?? width);
        const dx = (e.clientX - drag.current.x) * r;
        const dy = (e.clientY - drag.current.y) * r;
        if (Math.abs(dx) + Math.abs(dy) > 2) drag.current.moved = true;
        drag.current.x = e.clientX;
        drag.current.y = e.clientY;
        set(panBy(view, dx, dy));
      },
      onPointerUp: (e: React.PointerEvent<SVGSVGElement>) => {
        if (drag.current && !drag.current.moved && svgRef.current) {
          const rect = svgRef.current.getBoundingClientRect();
          onClick?.({ x: ((e.clientX - rect.left) * width) / rect.width, y: ((e.clientY - rect.top) * height) / rect.height });
        }
        drag.current = null;
        setDragging(false);
      },
      onDoubleClick: () => set(zoomBy(view, 1)),
    }),
  };
}
