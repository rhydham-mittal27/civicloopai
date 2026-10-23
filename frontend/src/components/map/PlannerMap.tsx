"use client";

import { useRef, useState } from "react";
import type { RoutePlan } from "@/lib/api";
import { toScreen, type LatLon } from "@/lib/map";
import { useMapView } from "@/lib/useMapView";
import { Icon } from "../ui";

const W = 1000;
const H = 760;

export interface Job {
  id: string;
  lat: number;
  lon: number;
  priority: number;
  volume: number;
  label: string;
}

interface Props {
  jobs: Job[];
  selected: Set<string>;
  onToggle: (id: string) => void;
  depot: LatLon | null;
  preview: RoutePlan | null;
  /** Draw the order the supervisor picked jobs in, dotted, under the optimised line. */
  compare: boolean;
  existing: RoutePlan[];
  showExisting: boolean;
}

const ROUTE_COLOURS = ["#0072b2", "#009e73", "#cc79a7", "#d55e00", "#56b4e9", "#8a6d00"];

export function PlannerMap({ jobs, selected, onToggle, depot, preview, compare, existing, showExisting }: Props) {
  const [tilesFailed, setTilesFailed] = useState(false);
  const [hover, setHover] = useState<string | null>(null);
  const svg = useRef<SVGSVGElement>(null);
  const points: LatLon[] = [...jobs.map((j) => ({ lat: j.lat, lon: j.lon })), ...(depot ? [depot] : [])];
  const map = useMapView(points, W, H, svg, 0.8);
  const at = (p: LatLon) => toScreen(map.view, W, H, p);
  const byId = new Map(jobs.map((j) => [j.id, j]));
  const previewOrder = preview ? preview.stops.map((s) => s.work_order_id) : [];
  const previewIndex = new Map(previewOrder.map((id, i) => [id, i + 1]));

  const pathOf = (ids: string[]) => {
    const pts = ids.map((id) => byId.get(id)).filter((j): j is Job => !!j).map((j) => at({ lat: j.lat, lon: j.lon }));
    if (depot) {
      const d = at(depot);
      return [d, ...pts, d];
    }
    return pts;
  };
  const line = (pts: { x: number; y: number }[]) => pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  const hovered = hover ? byId.get(hover) : null;

  return (
    <div className="sightings-frame planner-map">
      <svg
        ref={svg}
        viewBox={`0 0 ${W} ${H}`}
        role="group"
        aria-label="Map of jobs ready to route. Select a marker to add it to the route."
        data-dragging={map.dragging ? "" : undefined}
        {...map.handlers()}
      >
        <defs>
          <pattern id="pgrid" width="50" height="50" patternUnits="userSpaceOnUse">
            <path d="M50 0H0V50" fill="none" stroke="oklch(0.9 0.008 250)" strokeWidth="1" />
          </pattern>
          <filter id="p-shadow" x="-40%" y="-40%" width="180%" height="180%">
            <feDropShadow dx="0" dy="1.2" stdDeviation="1.4" floodColor="#14213d" floodOpacity="0.4" />
          </filter>
        </defs>
        <rect width={W} height={H} fill="oklch(0.965 0.006 250)" />
        <rect width={W} height={H} fill="url(#pgrid)" />
        {!tilesFailed && map.tiles.map((t) => <image key={t.key} className="map-tile" href={t.src} x={t.x} y={t.y} width={256} height={256} onError={() => setTilesFailed(true)} />)}
        <rect width={W} height={H} fill="oklch(0.2 0.03 258)" opacity="0.07" />

        {showExisting &&
          existing.map((plan, i) => {
            const pts = plan.stops.filter((s) => s.incident).map((s) => at({ lat: s.incident!.latitude, lon: s.incident!.longitude }));
            if (pts.length < 2) return null;
            const d = plan.depot ? at({ lat: plan.depot[0], lon: plan.depot[1] }) : null;
            const all = d ? [d, ...pts, d] : pts;
            return (
              <polyline key={plan.id} points={line(all)} className="planned-route" style={{ stroke: ROUTE_COLOURS[i % ROUTE_COLOURS.length], strokeDasharray: plan.approved_by ? undefined : "7 6" }}>
                <title>{`${plan.approved_by ? "Approved" : "Draft"} route, ${plan.stops.length} stops`}</title>
              </polyline>
            );
          })}

        {preview && compare && preview.selection_order && <polyline className="base-line" points={line(pathOf(preview.selection_order))} />}
        {preview && (
          <g>
            <polyline className="route-halo" points={line(pathOf(previewOrder))} />
            <polyline className="route-line" points={line(pathOf(previewOrder))} />
          </g>
        )}

        {depot && (
          <g transform={`translate(${at(depot).x} ${at(depot).y})`} filter="url(#p-shadow)">
            <polygon className="depot" points="0,-13 4,-4 13,-4 6,2 9,11 0,5 -9,11 -6,2 -13,-4 -4,-4" />
            <title>Depot</title>
          </g>
        )}

        {jobs.map((j) => {
          const { x, y } = at({ lat: j.lat, lon: j.lon });
          if (x < -30 || x > W + 30 || y < -30 || y > H + 30) return null;
          const on = selected.has(j.id);
          const urgent = j.priority >= 70;
          const r = 9 + (j.priority / 100) * 6;
          const n = previewIndex.get(j.id);
          return (
            <g
              key={j.id}
              className="pin job"
              transform={`translate(${x} ${y})`}
              tabIndex={0}
              role="checkbox"
              aria-checked={on}
              aria-label={`${j.label}, priority ${j.priority}, ${j.volume} cubic metres`}
              data-on={on ? "" : undefined}
              onClick={() => onToggle(j.id)}
              onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onToggle(j.id))}
              onMouseEnter={() => setHover(j.id)}
              onMouseLeave={() => setHover(null)}
              onFocus={() => setHover(j.id)}
              onBlur={() => setHover(null)}
            >
              <g filter="url(#p-shadow)">
                {on && <circle r={r + 6} fill="none" stroke="var(--accent)" strokeWidth="3" />}
                <circle r={r} fill={on ? "#b83a00" : urgent ? "#14213d" : "#ffffff"} stroke={on ? "#ffffff" : urgent ? "#ffffff" : "#475569"} strokeWidth={on || urgent ? 2.6 : 3} />
                {on && (
                  <text textAnchor="middle" dominantBaseline="central" className="pin-n">
                    {n ?? "✓"}
                  </text>
                )}
              </g>
              <title>{j.label}</title>
            </g>
          );
        })}
      </svg>

      <div className="sightings-zoom">
        <button type="button" className="btn" aria-label="Zoom in" onClick={map.zoomIn}>
          +
        </button>
        <button type="button" className="btn" aria-label="Zoom out" onClick={map.zoomOut}>
          −
        </button>
        <button type="button" className="btn" aria-label="Fit all jobs" title="Fit all" onClick={map.fit}>
          <Icon name="fit" />
        </button>
      </div>
      <span className="routemap-credit">{tilesFailed ? "Street map unavailable offline" : "© OpenStreetMap contributors"}</span>

      <div className="planner-key" aria-hidden="true">
        <span>
          <i className="key-dot key-open" /> Ready
        </span>
        <span>
          <i className="key-dot key-urgent" /> Urgent
        </span>
        <span>
          <i className="key-dot key-selected" /> In this route
        </span>
        {showExisting && (
          <span>
            <i className="key-line" /> Planned routes
          </span>
        )}
      </div>

      <div className="routemap-readout" aria-live="polite">
        {hovered ? (
          <>
            <strong>{hovered.label}</strong>
            <span className="muted">
              {" "}
              · priority {hovered.priority} · {hovered.volume} m³ · {selected.has(hovered.id) ? "click to remove" : "click to add"}
            </span>
          </>
        ) : (
          <span className="muted">Select markers to build a route. Drag to pan, double-click to zoom.</span>
        )}
      </div>
    </div>
  );
}
