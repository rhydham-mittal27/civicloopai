"use client";

import Link from "next/link";
import { useMemo, useRef, useState } from "react";
import type { DashboardSummary, IncidentStatus, MapPoint } from "@/lib/api";
import { fitView, panBy, project, tilesFor, toScreen, zoomBy, type View } from "@/lib/map";
import { MAP_CLOSED, MAP_PRIMARY, MAP_SECONDARY, STATUS_STYLE, shapePoints, type StatusStyle } from "@/lib/status";
import { Icon } from "../ui";

const W = 1000;
const H = 720;

export function Marker({ style, r, selected }: { style: StatusStyle; r: number; selected?: boolean }) {
  const common = {
    fill: style.hollow ? "#ffffff" : style.color,
    stroke: style.hollow ? style.color : "#ffffff",
    strokeWidth: style.hollow ? 3.2 : 2.4,
  };
  return (
    <g filter="url(#pin-shadow)">
      {selected && <circle r={r + 9} fill="none" stroke="#14213d" strokeWidth="2.5" strokeDasharray="4 3" />}
      {style.shape === "circle" || style.shape === "dot" ? (
        <circle r={style.shape === "dot" ? r * 0.7 : r} {...common} />
      ) : (
        <polygon points={shapePoints(style.shape, r)} strokeLinejoin="round" {...common} />
      )}
    </g>
  );
}

/** Tiny shape glyph used in legends and lists, so a colour is never the only cue. */
export function ShapeGlyph({ status, size = 16 }: { status: IncidentStatus; size?: number }) {
  const style = STATUS_STYLE[status];
  return (
    <svg width={size} height={size} viewBox="-10 -10 20 20" aria-hidden="true" className="glyph">
      <Marker style={style} r={6.5} />
    </svg>
  );
}

function ageLabel(hours: number) {
  if (hours < 1) return "under an hour";
  if (hours < 48) return `${Math.round(hours)} h`;
  return `${Math.round(hours / 24)} days`;
}

interface Props {
  points: MapPoint[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  hotspots?: DashboardSummary["hotspots"];
  focus?: { lat: number; lon: number; stamp: number } | null;
}

export function SightingsMap({ points, selectedId, onSelect, hotspots = [], focus }: Props) {
  const [on, setOn] = useState<Set<IncidentStatus>>(new Set(MAP_PRIMARY));
  const [showRepeat, setShowRepeat] = useState(true);
  const [tilesFailed, setTilesFailed] = useState(false);
  const [dragging, setDragging] = useState(false);
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const svg = useRef<SVGSVGElement>(null);

  const counts = useMemo(() => {
    const c: Partial<Record<IncidentStatus, number>> = {};
    points.forEach((p) => (c[p.status] = (c[p.status] ?? 0) + 1));
    return c;
  }, [points]);

  const visible = useMemo(() => points.filter((p) => on.has(p.status)), [points, on]);
  const initial = useMemo(() => fitView(visible.length ? visible.map((p) => ({ lat: p.latitude, lon: p.longitude })) : points.map((p) => ({ lat: p.latitude, lon: p.longitude })), W, H, 0.8), [visible, points]);
  const [override, setOverride] = useState<{ base: View; view: View } | null>(null);
  const [lastFocus, setLastFocus] = useState<number | null>(null);
  // a user's own pan/zoom wins until the data under it changes
  const view = override && override.base === initial ? override.view : initial;
  const setView = (next: View) => setOverride({ base: initial, view: next });

  if (focus && focus.stamp !== lastFocus) {
    setLastFocus(focus.stamp);
    const zoom = Math.max(view.zoom, 15);
    const centre = project(focus.lat, focus.lon, zoom);
    setOverride({ base: initial, view: { zoom, cx: centre.x, cy: centre.y } });
  }

  const tiles = useMemo(() => tilesFor(view, W, H), [view]);
  const selected = points.find((p) => p.id === selectedId) ?? null;
  const metersPerPixel = (lat: number) => (156543.03392 * Math.cos((lat * Math.PI) / 180)) / 2 ** view.zoom;

  const toggle = (statuses: IncidentStatus[]) =>
    setOn((current) => {
      const next = new Set(current);
      const allOn = statuses.every((s) => next.has(s));
      statuses.forEach((s) => (allOn ? next.delete(s) : next.add(s)));
      return next;
    });

  const ordered = [...visible].sort((a, b) => (a.id === selectedId ? 1 : 0) - (b.id === selectedId ? 1 : 0) || (a.risk ?? 0) - (b.risk ?? 0));

  return (
    <div className="sightings">
      <div className="sightings-legend" role="group" aria-label="Show on the map">
        {(
          [
            ...MAP_PRIMARY.map((s) => ({ key: s, statuses: [s] })),
            ...MAP_SECONDARY.map((s) => ({ key: s, statuses: [s] })),
            { key: "closed", statuses: MAP_CLOSED },
          ] as { key: string; statuses: IncidentStatus[] }[]
        ).map(({ key, statuses }) => {
          const status = statuses[0];
          const count = statuses.reduce((sum, s) => sum + (counts[s] ?? 0), 0);
          const active = statuses.every((s) => on.has(s));
          return (
            <button key={key} type="button" className="chip" aria-pressed={active} onClick={() => toggle(statuses)} title={active ? "Hide from the map" : "Show on the map"}>
              <ShapeGlyph status={status} />
              {key === "closed" ? "Closed this week" : STATUS_STYLE[status].label}
              <span className="chip-count">{count}</span>
            </button>
          );
        })}
        <button type="button" className="chip chip-ring" aria-pressed={showRepeat} onClick={() => setShowRepeat((v) => !v)}>
          <svg width="16" height="16" viewBox="-10 -10 20 20" aria-hidden="true">
            <circle r="7.5" fill="none" stroke="#14213d" strokeWidth="1.8" strokeDasharray="3 2.5" />
          </svg>
          Repeat sites
          <span className="chip-count">{hotspots.length}</span>
        </button>
      </div>

      <div className="sightings-frame">
        <svg
          ref={svg}
          viewBox={`0 0 ${W} ${H}`}
          role="group"
          aria-label={`Map of ${visible.length} sightings`}
          data-dragging={dragging ? "" : undefined}
          onPointerDown={(e) => {
            if ((e.target as Element).closest(".pin")) return;
            drag.current = { x: e.clientX, y: e.clientY, moved: false };
            (e.currentTarget as Element).setPointerCapture(e.pointerId);
            setDragging(true);
          }}
          onPointerMove={(e) => {
            if (!drag.current || !svg.current) return;
            const ratio = W / svg.current.getBoundingClientRect().width;
            const dx = (e.clientX - drag.current.x) * ratio;
            const dy = (e.clientY - drag.current.y) * ratio;
            if (Math.abs(dx) + Math.abs(dy) > 2) drag.current.moved = true;
            drag.current.x = e.clientX;
            drag.current.y = e.clientY;
            setView(panBy(view, dx, dy));
          }}
          onPointerUp={() => {
            if (drag.current && !drag.current.moved) onSelect(null);
            drag.current = null;
            setDragging(false);
          }}
          onDoubleClick={() => setView(zoomBy(view, 1))}
          onKeyDown={(e) => e.key === "Escape" && onSelect(null)}
        >
          <defs>
            <pattern id="sgrid" width="50" height="50" patternUnits="userSpaceOnUse">
              <path d="M50 0H0V50" fill="none" stroke="oklch(0.9 0.008 250)" strokeWidth="1" />
            </pattern>
            <filter id="pin-shadow" x="-40%" y="-40%" width="180%" height="180%">
              <feDropShadow dx="0" dy="1.2" stdDeviation="1.4" floodColor="#14213d" floodOpacity="0.4" />
            </filter>
          </defs>
          <rect width={W} height={H} fill="oklch(0.965 0.006 250)" />
          <rect width={W} height={H} fill="url(#sgrid)" />
          {!tilesFailed && tiles.map((t) => <image key={t.key} className="map-tile" href={t.src} x={t.x} y={t.y} width={256} height={256} onError={() => setTilesFailed(true)} />)}
          <rect width={W} height={H} fill="oklch(0.2 0.03 258)" opacity="0.07" />

          {showRepeat &&
            hotspots.map((h, i) => {
              const { x, y } = toScreen(view, W, H, { lat: h.latitude, lon: h.longitude });
              const r = Math.max(26, 300 / metersPerPixel(h.latitude));
              return (
                <g key={i} transform={`translate(${x} ${y})`} className="repeat-site">
                  <circle r={r} />
                  <title>{`Repeat site: ${h.reports_90d} reports in 90 days`}</title>
                </g>
              );
            })}

          {ordered.map((p) => {
            const { x, y } = toScreen(view, W, H, { lat: p.latitude, lon: p.longitude });
            if (x < -30 || x > W + 30 || y < -30 || y > H + 30) return null;
            const r = 8 + (p.risk ?? 0.35) * 6;
            const style = STATUS_STYLE[p.status];
            return (
              <g
                key={p.id}
                className="pin"
                transform={`translate(${x} ${y})`}
                tabIndex={0}
                role="button"
                aria-label={`${style.label}: ${p.description}${p.breached ? ", past its target time" : ""}`}
                aria-pressed={selectedId === p.id}
                onClick={() => onSelect(selectedId === p.id ? null : p.id)}
                onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onSelect(selectedId === p.id ? null : p.id))}
              >
                {p.breached && <circle r={r + 5.5} fill="none" stroke="var(--danger)" strokeWidth="2.6" />}
                <Marker style={style} r={r} selected={selectedId === p.id} />
                <title>{p.description}</title>
              </g>
            );
          })}
        </svg>

        <div className="sightings-zoom">
          <button type="button" className="btn" aria-label="Zoom in" onClick={() => setView(zoomBy(view, 1))}>
            +
          </button>
          <button type="button" className="btn" aria-label="Zoom out" onClick={() => setView(zoomBy(view, -1))}>
            −
          </button>
          <button type="button" className="btn" aria-label="Fit all sightings" title="Fit all" onClick={() => setOverride(null)}>
            <Icon name="fit" />
          </button>
        </div>
        <span className="routemap-credit">{tilesFailed ? "Street map unavailable offline" : "© OpenStreetMap contributors"}</span>

        {selected ? (
          <article className="sightings-card" aria-live="polite">
            <header>
              <span className="badge" data-status={selected.status}>
                {STATUS_STYLE[selected.status].label}
              </span>
              {selected.breached && <span className="flag">Past target</span>}
              <button type="button" className="btn btn-quiet" aria-label="Close details" onClick={() => onSelect(null)}>
                ×
              </button>
            </header>
            <p className="sightings-card-title">{selected.description}</p>
            <dl>
              <div>
                <dt>Open for</dt>
                <dd>{ageLabel(selected.age_hours)}</dd>
              </div>
              <div>
                <dt>Severity</dt>
                <dd style={{ textTransform: "capitalize" }}>{selected.severity ?? "not rated"}</dd>
              </div>
              <div>
                <dt>Risk</dt>
                <dd>{selected.risk === null ? "–" : Math.round(selected.risk * 100)}</dd>
              </div>
            </dl>
            <Link className="btn btn-primary" href={`/incidents/${selected.id}`}>
              Open report
            </Link>
          </article>
        ) : (
          <span className="sightings-hint muted">Drag to pan, double-click to zoom. Marker size shows risk; a red ring means past its target time.</span>
        )}
      </div>
    </div>
  );
}
