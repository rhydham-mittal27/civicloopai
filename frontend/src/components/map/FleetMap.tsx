"use client";

import { useMemo, useRef, useState } from "react";
import type { MapPoint, TrailPoint, Vehicle, VehicleState } from "@/lib/api";
import { project, type LatLon } from "@/lib/map";
import { useMapView } from "@/lib/useMapView";
import { MAP_PRIMARY, STATUS_STYLE } from "@/lib/status";
import { Icon } from "../ui";

const W = 1000;
const H = 720;

export const STATE_LABEL: Record<VehicleState, string> = {
  moving: "Moving",
  idle: "Stopped",
  stale: "Signal weak",
  offline: "Offline",
  no_signal: "No signal yet",
  disabled: "Switched off",
};

const STATE_COLOR: Record<VehicleState, string> = {
  moving: "#1f9d82",
  idle: "#e0a100",
  stale: "#6b7a99",
  offline: "#9aa3b8",
  no_signal: "#9aa3b8",
  disabled: "#9aa3b8",
};

/** A vehicle on the map. The shape tells the state as well as the colour. */
function VehicleGlyph({ state, heading, selected }: { state: VehicleState; heading: number | null; selected: boolean }) {
  const colour = STATE_COLOR[state];
  const faded = state === "offline";
  return (
    <g>
      {selected && <circle r="27" fill="none" stroke="#14213d" strokeWidth="2.5" strokeDasharray="5 4" />}
      {state === "stale" && <circle r="21" fill="none" stroke={colour} strokeWidth="2" strokeDasharray="3 3" />}
      <circle r="16" fill={faded ? "#ffffff" : colour} stroke={faded ? colour : "#ffffff"} strokeWidth={faded ? 3 : 3.2} filter="url(#fleet-shadow)" />
      {state === "moving" && (
        <g transform={`rotate(${heading ?? 0})`}>
          <path d="M0 -9 L7 6 L0 2.5 L-7 6 Z" fill="#ffffff" />
        </g>
      )}
      {state === "idle" && (
        <g fill="#ffffff">
          <rect x="-6" y="-6.5" width="4.4" height="13" rx="1.2" />
          <rect x="1.6" y="-6.5" width="4.4" height="13" rx="1.2" />
        </g>
      )}
      {state === "stale" && <circle r="4" fill="#ffffff" />}
      {(state === "offline" || state === "no_signal") && <path d="M-5 -5 L5 5 M5 -5 L-5 5" stroke={colour} strokeWidth="2.6" strokeLinecap="round" />}
    </g>
  );
}

interface Props {
  vehicles: Vehicle[];
  sightings: MapPoint[];
  trail: TrailPoint[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  focus?: { lat: number; lon: number; stamp: number } | null;
}

export function FleetMap({ vehicles, sightings, trail, selectedId, onSelect, focus }: Props) {
  const svg = useRef<SVGSVGElement>(null);
  const [tilesFailed, setTilesFailed] = useState(false);
  const [showSightings, setShowSightings] = useState(true);
  const [lastFocus, setLastFocus] = useState<number | null>(null);

  const located = vehicles.filter((v) => v.lat !== null && v.lon !== null && v.is_active);
  // Fit the map when the set of vehicles changes, never on every position update, so a person's own pan and zoom survives.
  const idsKey = located.map((v) => v.id).join(",");
  const anchor = useMemo<LatLon[]>(
    () => (located.length ? located.map((v) => ({ lat: v.lat as number, lon: v.lon as number })) : sightings.map((p) => ({ lat: p.latitude, lon: p.longitude }))),
    [idsKey, located.length === 0 ? sightings.length : 0], // eslint-disable-line react-hooks/exhaustive-deps
  );
  const map = useMapView(anchor, W, H, svg, 0.7);

  if (focus && focus.stamp !== lastFocus) {
    setLastFocus(focus.stamp);
    map.centreOn({ lat: focus.lat, lon: focus.lon }, 16);
  }

  const { view } = map;
  const world = (lat: number, lon: number) => project(lat, lon, view.zoom);
  const metresPerPixel = (lat: number) => (156543.03392 * Math.cos((lat * Math.PI) / 180)) / 2 ** view.zoom;
  const selected = vehicles.find((v) => v.id === selectedId) ?? null;
  const trailPath = trail.map((p) => {
    const { x, y } = world(p.lat, p.lon);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const ordered = [...located].sort((a, b) => (a.id === selectedId ? 1 : 0) - (b.id === selectedId ? 1 : 0));
  const visibleSightings = sightings.filter((p) => (MAP_PRIMARY as string[]).includes(p.status));

  return (
    <div className="sightings fleetmap">
      <div className="sightings-legend" role="group" aria-label="Map key">
        {(["moving", "idle", "stale", "offline"] as VehicleState[]).map((s) => (
          <span key={s} className="chip chip-static">
            <svg width="22" height="22" viewBox="-20 -20 40 40" aria-hidden="true">
              <VehicleGlyph state={s} heading={0} selected={false} />
            </svg>
            {STATE_LABEL[s]}
            <span className="chip-count">{vehicles.filter((v) => v.state === s).length}</span>
          </span>
        ))}
        <button type="button" className="chip" aria-pressed={showSightings} onClick={() => setShowSightings((v) => !v)}>
          <svg width="16" height="16" viewBox="-10 -10 20 20" aria-hidden="true">
            <circle r="5" fill="#2563a8" opacity="0.7" />
          </svg>
          Open reports
          <span className="chip-count">{visibleSightings.length}</span>
        </button>
      </div>

      <div className="sightings-frame">
        <svg
          ref={svg}
          viewBox={`0 0 ${W} ${H}`}
          role="group"
          aria-label={`Live map of ${located.length} vehicles`}
          data-dragging={map.dragging ? "" : undefined}
          {...map.handlers(() => onSelect(null))}
          onKeyDown={(e) => e.key === "Escape" && onSelect(null)}
        >
          <defs>
            <pattern id="fgrid" width="50" height="50" patternUnits="userSpaceOnUse">
              <path d="M50 0H0V50" fill="none" stroke="oklch(0.9 0.008 250)" strokeWidth="1" />
            </pattern>
            <filter id="fleet-shadow" x="-50%" y="-50%" width="200%" height="200%">
              <feDropShadow dx="0" dy="1.6" stdDeviation="2" floodColor="#14213d" floodOpacity="0.4" />
            </filter>
          </defs>
          <rect width={W} height={H} fill="oklch(0.965 0.006 250)" />
          <rect width={W} height={H} fill="url(#fgrid)" />
          {!tilesFailed && map.tiles.map((t) => <image key={t.key} className="map-tile" href={t.src} x={t.x} y={t.y} width={256} height={256} onError={() => setTilesFailed(true)} />)}
          <rect width={W} height={H} fill="oklch(0.2 0.03 258)" opacity="0.07" />

          {/* everything below is in world pixels at this zoom, so panning is one transform and markers can glide */}
          <g transform={`translate(${W / 2 - view.cx} ${H / 2 - view.cy})`}>
            <g key={view.zoom}>
              {showSightings &&
                visibleSightings.map((p) => {
                  const { x, y } = world(p.latitude, p.longitude);
                  return <circle key={p.id} cx={x} cy={y} r={p.breached ? 6.5 : 5} fill={STATUS_STYLE[p.status].color} opacity="0.6" stroke="#ffffff" strokeWidth="1.5" />;
                })}

              {selected?.lat != null && selected.accuracy_m ? (
                <circle
                  cx={world(selected.lat, selected.lon as number).x}
                  cy={world(selected.lat, selected.lon as number).y}
                  r={Math.max(12, selected.accuracy_m / metresPerPixel(selected.lat))}
                  className="accuracy"
                />
              ) : null}

              {trailPath.length > 1 && (
                <>
                  <polyline points={trailPath.join(" ")} className="trail-casing" />
                  <polyline points={trailPath.join(" ")} className="trail-line" />
                </>
              )}

              {ordered.map((v) => {
                const { x, y } = world(v.lat as number, v.lon as number);
                const isSelected = v.id === selectedId;
                return (
                  <g
                    key={v.id}
                    className="pin vehicle"
                    style={{ transform: `translate(${x}px, ${y}px)` }}
                    tabIndex={0}
                    role="button"
                    aria-label={`${v.label}, ${STATE_LABEL[v.state]}${v.speed_kmh !== null ? `, ${Math.round(v.speed_kmh)} kilometres an hour` : ""}`}
                    aria-pressed={isSelected}
                    onClick={() => onSelect(isSelected ? null : v.id)}
                    onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onSelect(isSelected ? null : v.id))}
                  >
                    <VehicleGlyph state={v.state} heading={v.heading} selected={isSelected} />
                    <g transform="translate(0 30)">
                      <rect x={-(v.label.length * 4.4 + 9)} y="-10" width={v.label.length * 8.8 + 18} height="20" rx="10" className="vehicle-tag" />
                      <text textAnchor="middle" y="4.5" className="vehicle-tag-text">
                        {v.label}
                      </text>
                    </g>
                  </g>
                );
              })}
            </g>
          </g>
        </svg>

        <div className="sightings-zoom">
          <button type="button" className="btn" aria-label="Zoom in" onClick={map.zoomIn}>
            +
          </button>
          <button type="button" className="btn" aria-label="Zoom out" onClick={map.zoomOut}>
            −
          </button>
          <button type="button" className="btn" aria-label="Show all vehicles" title="Show all vehicles" onClick={map.fit}>
            <Icon name="fit" />
          </button>
        </div>
        <span className="routemap-credit">{tilesFailed ? "Street map unavailable offline" : "© OpenStreetMap contributors"}</span>
        {located.length === 0 && <span className="picker-hint">No vehicle has reported a position yet</span>}
      </div>
    </div>
  );
}
