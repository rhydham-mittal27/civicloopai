"use client";

import Link from "next/link";
import { useMemo, useState, useSyncExternalStore } from "react";
import type { RoutePlan } from "@/lib/api";
import { Icon } from "./ui";

const W = 960;
const H = 500;
const TILE = 256;

type Mode = "optimised" | "nearest" | "selection";
type View = "google" | "compare";
interface LatLon {
  lat: number;
  lon: number;
}
interface Point extends LatLon {
  id: string;
  priority: number;
  label: string;
}

/** Web-Mercator pixel position of a coordinate at a zoom level. */
function project(lat: number, lon: number, zoom: number) {
  const scale = TILE * 2 ** zoom;
  const sin = Math.sin((lat * Math.PI) / 180);
  return { x: ((lon + 180) / 360) * scale, y: (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * scale };
}

function km(a: LatLon, b: LatLon) {
  const r = (d: number) => (d * Math.PI) / 180;
  const h = Math.sin(r(b.lat - a.lat) / 2) ** 2 + Math.cos(r(a.lat)) * Math.cos(r(b.lat)) * Math.sin(r(b.lon - a.lon) / 2) ** 2;
  return 2 * 6371.0088 * Math.asin(Math.sqrt(h));
}

function length(order: Point[], depot: LatLon | null) {
  const pts = depot ? [depot, ...order, depot] : order;
  return pts.slice(1).reduce((sum, p, i) => sum + km(pts[i], p), 0);
}

const ll = (p: LatLon) => `${p.lat},${p.lon}`;

/** Splits the stop sequence into parts the Google embed can draw in one go (shared end points). */
function parts(depot: LatLon | null, order: Point[], maxWaypoints: number): LatLon[][] {
  const pts: LatLon[] = depot ? [depot, ...order, depot] : [...order];
  const out: LatLon[][] = [];
  const span = maxWaypoints + 1;
  for (let start = 0; start < pts.length - 1; start += span) out.push(pts.slice(start, Math.min(start + span + 1, pts.length)));
  return out;
}

/** Google Maps embed for one part of the route. The official embed needs a key; without one the classic embed works. */
function embedUrl(part: LatLon[], apiKey: string | undefined) {
  const origin = part[0];
  const destination = part[part.length - 1];
  const mid = part.slice(1, -1);
  if (apiKey) {
    const waypoints = mid.length ? `&waypoints=${encodeURIComponent(mid.map(ll).join("|"))}` : "";
    return `https://www.google.com/maps/embed/v1/directions?key=${encodeURIComponent(apiKey)}&origin=${ll(origin)}&destination=${ll(destination)}${waypoints}&mode=driving`;
  }
  const daddr = [...mid, destination].map(ll).join("+to:");
  return `https://maps.google.com/maps?saddr=${ll(origin)}&daddr=${daddr}&dirflg=d&hl=en&output=embed`;
}

function directionsUrl(part: LatLon[]) {
  const mid = part.slice(1, -1).map(ll).join("|");
  return `https://www.google.com/maps/dir/?api=1&origin=${ll(part[0])}&destination=${ll(part[part.length - 1])}${mid ? `&waypoints=${encodeURIComponent(mid)}` : ""}&travelmode=driving`;
}

const reducedMotionQuery = "(prefers-reduced-motion: reduce)";
function useReducedMotion() {
  return useSyncExternalStore(
    (notify) => {
      const query = window.matchMedia(reducedMotionQuery);
      query.addEventListener("change", notify);
      return () => query.removeEventListener("change", notify);
    },
    () => window.matchMedia(reducedMotionQuery).matches,
    () => false,
  );
}

function stopsOf(plan: RoutePlan) {
  const byId = new Map<string, Point>();
  plan.stops.forEach((stop) => {
    if (!stop.incident) return;
    byId.set(stop.work_order_id, {
      id: stop.work_order_id,
      lat: stop.incident.latitude,
      lon: stop.incident.longitude,
      priority: stop.priority ?? 0,
      label: stop.incident.description,
    });
  });
  const pick = (ids: string[] | null | undefined) => (ids ?? []).map((id) => byId.get(id)).filter((p): p is Point => !!p);
  return {
    optimised: plan.stops.map((s) => byId.get(s.work_order_id)).filter((p): p is Point => !!p),
    nearest: pick(plan.greedy_order),
    selection: pick(plan.selection_order),
    depot: plan.depot ? { lat: plan.depot[0], lon: plan.depot[1] } : null,
  };
}

/* ------------------------------------------------------------------ wrapper */

export function RouteMap({ plan }: { plan: RoutePlan }) {
  const [view, setView] = useState<View>("google");
  const { optimised, depot } = useMemo(() => stopsOf(plan), [plan]);
  const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;
  const embedParts = useMemo(() => parts(depot, optimised, apiKey ? 20 : 12), [depot, optimised, apiKey]);
  const linkParts = useMemo(() => parts(depot, optimised, 9), [depot, optimised]);

  return (
    <section className="routemap" aria-labelledby="map-title">
      <div className="routemap-head">
        <h2 id="map-title">Route map</h2>
        <div className="segmented" role="radiogroup" aria-label="Map type">
          {(
            [
              ["google", "Google Maps (roads)"],
              ["compare", "Optimisation view"],
            ] as const
          ).map(([value, label]) => (
            <label key={value}>
              <input className="sr-only" type="radio" name="map-view" value={value} checked={view === value} onChange={() => setView(value)} />
              <span>{label}</span>
            </label>
          ))}
        </div>
        {linkParts.map((part, i) => (
          <a key={i} className="btn" href={directionsUrl(part)} target="_blank" rel="noreferrer">
            <Icon name="pin" />
            {linkParts.length === 1 ? "Open in Google Maps" : `Google Maps, part ${i + 1} of ${linkParts.length}`}
          </a>
        ))}
      </div>

      {view === "google" ? <GoogleFrame partsList={embedParts} stops={optimised.length} hasDepot={!!depot} /> : <OptimisationMap plan={plan} />}
    </section>
  );
}

/* ------------------------------------------------------------------ Google iframe */

function GoogleFrame({ partsList, stops, hasDepot }: { partsList: LatLon[][]; stops: number; hasDepot: boolean }) {
  const [index, setIndex] = useState(0);
  const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;
  const part = partsList[Math.min(index, partsList.length - 1)];
  return (
    <div className="gframe-wrap">
      {partsList.length > 1 && (
        <div className="segmented" role="radiogroup" aria-label="Route part">
          {partsList.map((_, i) => (
            <label key={i}>
              <input className="sr-only" type="radio" name="map-part" checked={index === i} onChange={() => setIndex(i)} />
              <span>
                Part {i + 1} of {partsList.length}
              </span>
            </label>
          ))}
        </div>
      )}
      <div className="routemap-frame gframe">
        <iframe
          key={part.map(ll).join("/")}
          title={`Google Maps driving route through ${stops} stops`}
          src={embedUrl(part, apiKey)}
          loading="lazy"
          allowFullScreen
          referrerPolicy="no-referrer-when-downgrade"
        />
      </div>
      <p className="hint muted">
        The blue line is the real driving route Google Maps finds through the stops, in the planned order{hasDepot ? ", starting and ending at the depot" : ""}. Its distance and time are the
        real road figures, usually longer than the straight-line estimates. Zoom and drag to inspect it, or open it in Google Maps for turn-by-turn directions on a phone.
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ optimisation view */

function OptimisationMap({ plan }: { plan: RoutePlan }) {
  const [mode, setMode] = useState<Mode>("optimised");
  const [replay, setReplay] = useState(0);
  const [active, setActive] = useState<string | null>(null);
  const [tilesFailed, setTilesFailed] = useState(false);
  const reduced = useReducedMotion();

  const model = useMemo(() => {
    const { optimised, nearest, selection, depot } = stopsOf(plan);
    const all: LatLon[] = [...optimised, ...(depot ? [depot] : [])];
    let zoom = 15;
    for (let z = 17; z >= 8; z--) {
      const px = all.map((p) => project(p.lat, p.lon, z));
      const w = Math.max(...px.map((p) => p.x)) - Math.min(...px.map((p) => p.x));
      const h = Math.max(...px.map((p) => p.y)) - Math.min(...px.map((p) => p.y));
      if (w <= W * 0.74 && h <= H * 0.7) {
        zoom = z;
        break;
      }
    }
    const px = all.map((p) => project(p.lat, p.lon, zoom));
    const cx = (Math.max(...px.map((p) => p.x)) + Math.min(...px.map((p) => p.x))) / 2;
    const cy = (Math.max(...px.map((p) => p.y)) + Math.min(...px.map((p) => p.y))) / 2;
    const ox = cx - W / 2;
    const oy = cy - H / 2;
    const at = (p: LatLon) => {
      const { x, y } = project(p.lat, p.lon, zoom);
      return { x: x - ox, y: y - oy };
    };
    const tiles: { key: string; x: number; y: number; src: string }[] = [];
    const max = 2 ** zoom;
    for (let tx = Math.floor(ox / TILE); tx <= Math.floor((ox + W) / TILE); tx++) {
      for (let ty = Math.floor(oy / TILE); ty <= Math.floor((oy + H) / TILE); ty++) {
        if (ty < 0 || ty >= max) continue;
        const wrapped = ((tx % max) + max) % max;
        tiles.push({ key: `${tx}/${ty}`, x: tx * TILE - ox, y: ty * TILE - oy, src: `https://tile.openstreetmap.org/${zoom}/${wrapped}/${ty}.png` });
      }
    }
    return {
      optimised,
      nearest,
      selection,
      depot,
      at,
      tiles,
      distances: {
        optimised: length(optimised, depot),
        nearest: nearest.length === optimised.length ? length(nearest, depot) : null,
        selection: selection.length === optimised.length ? length(selection, depot) : null,
      },
    };
  }, [plan]);

  const baseline = mode === "nearest" ? model.nearest : mode === "selection" ? model.selection : [];
  const comparing = mode !== "optimised" && baseline.length > 0;
  const withDepot = (order: Point[]) => {
    const pts = order.map(model.at);
    if (model.depot) {
      const d = model.at(model.depot);
      return [d, ...pts, d];
    }
    return pts;
  };
  const line = (pts: { x: number; y: number }[]) => pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  const route = withDepot(model.optimised);
  const baseLine = comparing ? withDepot(baseline) : [];
  const motionPath = route.map((p, i) => `${i ? "L" : "M"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  const duration = Math.max(6, model.optimised.length * 1.4);
  const focus = model.optimised.findIndex((p) => p.id === active);
  const focusStop = focus >= 0 ? plan.stops[focus] : null;

  const saved = (from: number | null) => (from && from > 0 ? (from - model.distances.optimised) / from : null);
  const options: { value: Mode; label: string; ready: boolean }[] = [
    { value: "optimised", label: "Optimised route", ready: true },
    { value: "nearest", label: "vs nearest-neighbour", ready: model.nearest.length > 0 },
    { value: "selection", label: "vs selection order", ready: model.selection.length > 0 },
  ];

  return (
    <div className="optmap">
      <div className="routemap-head">
        <div className="segmented" role="radiogroup" aria-label="Compare with">
          {options.map((o) => (
            <label key={o.value} aria-disabled={!o.ready} title={o.ready ? undefined : "This route was planned before comparisons were recorded"}>
              <input
                className="sr-only"
                type="radio"
                name="map-mode"
                value={o.value}
                checked={mode === o.value}
                disabled={!o.ready}
                onChange={() => {
                  setMode(o.value);
                  setReplay((n) => n + 1);
                }}
              />
              <span>{o.label}</span>
            </label>
          ))}
        </div>
        <button type="button" className="btn" onClick={() => setReplay((n) => n + 1)}>
          <Icon name="replay" />
          Replay
        </button>
      </div>

      <div className="routemap-frame">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Map of the route through ${model.optimised.length} stops`}>
          <defs>
            <pattern id="grid" width="48" height="48" patternUnits="userSpaceOnUse">
              <path d="M48 0H0V48" fill="none" stroke="oklch(0.9 0.008 250)" strokeWidth="1" />
            </pattern>
            <filter id="soft" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="1" stdDeviation="1.5" floodColor="#14213d" floodOpacity="0.35" />
            </filter>
          </defs>
          <rect width={W} height={H} fill="oklch(0.965 0.006 250)" />
          <rect width={W} height={H} fill="url(#grid)" />
          {!tilesFailed &&
            model.tiles.map((t) => (
              <image key={t.key} className="map-tile" href={t.src} x={t.x} y={t.y} width={TILE} height={TILE} onError={() => setTilesFailed(true)} />
            ))}
          <rect width={W} height={H} fill="oklch(0.2 0.03 258)" opacity="0.06" />

          {comparing && (
            <g key={`base-${mode}-${replay}`}>
              <polyline className={reduced ? "base-line" : "base-line draw-base"} pathLength={1} points={line(baseLine)} />
            </g>
          )}

          <g key={`route-${mode}-${replay}`}>
            <polyline className={reduced ? "route-halo" : comparing ? "route-halo draw draw-late" : "route-halo draw"} pathLength={1} points={line(route)} />
            <polyline className={reduced ? "route-line" : comparing ? "route-line draw draw-late" : "route-line draw"} pathLength={1} points={line(route)} />
            {!reduced &&
              route.slice(1).map((p, i) => {
                const a = route[i];
                const angle = (Math.atan2(p.y - a.y, p.x - a.x) * 180) / Math.PI;
                const len = Math.hypot(p.x - a.x, p.y - a.y);
                if (len < 46) return null;
                return (
                  <path key={i} className="route-arrow" d="M-5,-4.5 L3,0 L-5,4.5" transform={`translate(${(a.x + p.x) / 2} ${(a.y + p.y) / 2}) rotate(${angle})`} />
                );
              })}
            {!reduced && route.length > 1 && (
              <g className="vehicle" filter="url(#soft)">
                <circle r="8" />
                <circle r="3" className="vehicle-core" />
                <animateMotion dur={`${duration}s`} repeatCount="indefinite" path={motionPath} rotate="auto" begin={comparing ? "2.4s" : "0.6s"} />
              </g>
            )}
          </g>

          {model.depot && (
            <g transform={`translate(${model.at(model.depot).x} ${model.at(model.depot).y})`} filter="url(#soft)">
              <polygon className="depot" points="0,-13 4,-4 13,-4 6,2 9,11 0,5 -9,11 -6,2 -13,-4 -4,-4" />
              <title>Depot</title>
            </g>
          )}

          {model.optimised.map((p, i) => {
            const { x, y } = model.at(p);
            const stop = plan.stops[i];
            const urgent = p.priority >= 70;
            return (
              <Link key={p.id} href={stop.incident ? `/incidents/${stop.incident.id}` : "#"} aria-label={`Stop ${i + 1}: ${p.label}`}>
                <g transform={`translate(${x} ${y})`}>
                  <g
                    className="stop"
                    data-active={active === p.id ? "" : undefined}
                    data-urgent={urgent ? "" : undefined}
                    onMouseEnter={() => setActive(p.id)}
                    onMouseLeave={() => setActive(null)}
                    onFocus={() => setActive(p.id)}
                    onBlur={() => setActive(null)}
                    style={{ animationDelay: reduced ? undefined : `${0.15 + i * 0.07}s` }}
                  >
                    <circle r={urgent ? 16 : 13} filter="url(#soft)" />
                    <text textAnchor="middle" dominantBaseline="central">
                      {i + 1}
                    </text>
                    <title>{p.label}</title>
                  </g>
                </g>
              </Link>
            );
          })}
        </svg>

        <div className="routemap-readout" aria-live="polite">
          {focusStop?.incident ? (
            <>
              <strong>Stop {focus + 1}</strong> {focusStop.incident.description}
              <span className="muted">
                {" "}
                · priority {focusStop.priority ?? "–"} · {focusStop.planned_volume ?? 0} m³
              </span>
            </>
          ) : (
            <span className="muted">Hover or tab to a stop for details. Select it to open the report.</span>
          )}
        </div>
        <span className="routemap-credit">{tilesFailed ? "Street map unavailable offline" : "© OpenStreetMap contributors"}</span>
      </div>

      <dl className="routemap-stats">
        <div data-on={mode === "optimised" ? "" : undefined}>
          <dt>
            <i className="swatch swatch-route" /> Optimised (OR-Tools)
          </dt>
          <dd>{model.distances.optimised.toFixed(1)} km</dd>
        </div>
        <div data-on={mode === "nearest" ? "" : undefined}>
          <dt>
            <i className="swatch swatch-base" /> Nearest-neighbour
          </dt>
          <dd>
            {model.distances.nearest === null ? "–" : `${model.distances.nearest.toFixed(1)} km`}
            {saved(model.distances.nearest) !== null && <small>{formatDelta(saved(model.distances.nearest)!)}</small>}
          </dd>
        </div>
        <div data-on={mode === "selection" ? "" : undefined}>
          <dt>
            <i className="swatch swatch-base" /> In selection order
          </dt>
          <dd>
            {model.distances.selection === null ? "–" : `${model.distances.selection.toFixed(1)} km`}
            {saved(model.distances.selection) !== null && <small>{formatDelta(saved(model.distances.selection)!)}</small>}
          </dd>
        </div>
      </dl>
      <p className="hint muted">Straight-line distances, to compare planners. Switch to Google Maps for the real road route.</p>
    </div>
  );
}

function formatDelta(ratio: number) {
  if (Math.abs(ratio) < 0.005) return "same length";
  return ratio > 0 ? `optimised is ${Math.round(ratio * 100)}% shorter` : `optimised is ${Math.round(-ratio * 100)}% longer`;
}
