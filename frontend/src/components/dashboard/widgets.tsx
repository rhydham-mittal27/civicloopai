"use client";

import Link from "next/link";
import type { AttentionItem, DashboardSummary, IncidentStatus } from "@/lib/api";
import { STATUS_STYLE } from "@/lib/status";
import { ShapeGlyph } from "../map/SightingsMap";
import { Icon, formatWhen } from "../ui";

export type Band = "good" | "warn" | "bad" | "neutral";
const BAND_LABEL: Record<Band, string> = { good: "On track", warn: "Watch", bad: "Act now", neutral: "" };

export function hours(value: number | null | undefined): string {
  if (value === null || value === undefined) return "–";
  if (value < 1) return "under 1 h";
  if (value < 48) return `${Math.round(value)} h`;
  return `${(value / 24).toFixed(1)} days`;
}

/** A ring that fills to `value` (0 to 1), ending in a dot, like a progress gauge. */
function Ring({ value, label }: { value: number; label: string }) {
  const r = 22;
  const c = 2 * Math.PI * r;
  const v = Math.max(0.02, Math.min(1, value));
  const angle = v * 2 * Math.PI - Math.PI / 2;
  return (
    <span className="ring" role="img" aria-label={label}>
      <svg viewBox="0 0 60 60" aria-hidden="true">
        <circle cx="30" cy="30" r={r} className="ring-track" />
        <circle cx="30" cy="30" r={r} className="ring-arc" strokeDasharray={`${c * v} ${c}`} transform="rotate(-90 30 30)" />
        <circle cx={30 + r * Math.cos(angle)} cy={30 + r * Math.sin(angle)} r="4.6" className="ring-dot" />
      </svg>
      <span className="ring-label">{label}</span>
    </span>
  );
}

export function KpiCard({
  label,
  value,
  secondary,
  detail,
  band = "neutral",
  href,
  hint,
  icon,
  ring,
  ringLabel,
}: {
  label: string;
  value: React.ReactNode;
  /** A smaller grey figure shown beside the value, such as the total it is out of. */
  secondary?: React.ReactNode;
  detail?: React.ReactNode;
  band?: Band;
  href?: string;
  hint?: string;
  icon?: Parameters<typeof Icon>[0]["name"];
  /** 0 to 1. Leave out when there is no meaningful ratio. */
  ring?: number | null;
  ringLabel?: string;
}) {
  const body = (
    <>
      <div className="kpi-top">
        {icon && (
          <span className="kpi-icon">
            <Icon name={icon} />
          </span>
        )}
        <span className="kpi-label">{label}</span>
      </div>
      <div className="kpi-main">
        <div className="kpi-value">
          {value}
          {secondary !== undefined && <span className="kpi-sec">{secondary}</span>}
        </div>
        {ring !== null && ring !== undefined && <Ring value={ring} label={ringLabel ?? `${Math.round(ring * 100)}%`} />}
      </div>
      <div className="kpi-detail">
        {band !== "neutral" && band !== "good" && (
          <span className="kpi-band" data-band={band}>
            {BAND_LABEL[band]}
          </span>
        )}
        {detail}
      </div>
    </>
  );
  return href ? (
    <Link href={href} className="kpi" data-band={band} title={hint}>
      {body}
    </Link>
  ) : (
    <div className="kpi" data-band={band} title={hint}>
      {body}
    </div>
  );
}

/* ------------------------------------------------------------------ flow */

export function FlowChart({ flow }: { flow: DashboardSummary["flow"] }) {
  const max = Math.max(4, ...flow.flatMap((d) => [d.created, d.closed]));
  const W = 560;
  const H = 190;
  const pad = { l: 28, r: 6, t: 10, b: 26 };
  const slot = (W - pad.l - pad.r) / flow.length;
  const bar = Math.min(14, slot / 2.6);
  const y = (v: number) => pad.t + (H - pad.t - pad.b) * (1 - v / max);
  const created = flow.reduce((s, d) => s + d.created, 0);
  const closed = flow.reduce((s, d) => s + d.closed, 0);
  const ticks = [0, Math.round(max / 2), max];
  return (
    <figure className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Reports received and closed per day over ${flow.length} days: ${created} received, ${closed} closed`}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} className="gridline" />
            <text x={pad.l - 6} y={y(t) + 4} textAnchor="end" className="axis">
              {t}
            </text>
          </g>
        ))}
        {flow.map((d, i) => {
          const x = pad.l + slot * i + slot / 2;
          const day = new Date(d.date + "T00:00:00");
          return (
            <g key={d.date}>
              <rect x={x - bar - 1} y={y(d.created)} width={bar} height={Math.max(0, H - pad.b - y(d.created))} rx="2" className="bar-created">
                <title>{`${d.date}: ${d.created} received`}</title>
              </rect>
              <rect x={x + 1} y={y(d.closed)} width={bar} height={Math.max(0, H - pad.b - y(d.closed))} rx="2" className="bar-closed">
                <title>{`${d.date}: ${d.closed} closed`}</title>
              </rect>
              {(i % 2 === 0 || flow.length <= 8) && (
                <text x={x} y={H - 8} textAnchor="middle" className="axis">
                  {day.getDate()}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      <figcaption>
        <span>
          <i className="swatch-box bar-created" /> Received <strong>{created}</strong>
        </span>
        <span>
          <i className="swatch-box bar-closed" /> Closed <strong>{closed}</strong>
        </span>
        <span className="muted">{created > closed ? `Backlog grew by ${created - closed}` : created < closed ? `Backlog shrank by ${closed - created}` : "Backlog steady"}</span>
      </figcaption>
    </figure>
  );
}

/* ------------------------------------------------------------------ ageing */

export function AgingChart({ aging }: { aging: DashboardSummary["aging"] }) {
  const statuses = Object.keys(aging.series) as IncidentStatus[];
  const totals = aging.buckets.map((_, b) => statuses.reduce((s, st) => s + aging.series[st][b], 0));
  const max = Math.max(1, ...totals);
  return (
    <div className="aging">
      {aging.buckets.map((bucket, b) => (
        <div key={bucket} className="aging-row" data-old={b === aging.buckets.length - 1 && totals[b] > 0 ? "" : undefined}>
          <span className="aging-label">{bucket}</span>
          <div className="aging-track" role="img" aria-label={`${totals[b]} open reports ${bucket}`}>
            {statuses.map((st) => {
              const n = aging.series[st][b];
              return n > 0 ? (
                <span key={st} style={{ width: `${(n / max) * 100}%`, background: STATUS_STYLE[st].color }} title={`${STATUS_STYLE[st].label}: ${n}`}>
                  {n}
                </span>
              ) : null;
            })}
          </div>
          <strong className="aging-total">{totals[b]}</strong>
        </div>
      ))}
      <ul className="aging-legend">
        {statuses.map((st) => (
          <li key={st}>
            <ShapeGlyph status={st} size={14} />
            {STATUS_STYLE[st].label}
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ------------------------------------------------------------------ attention */

const KIND: Record<AttentionItem["kind"], { label: string; tone: "bad" | "warn" | "neutral" }> = {
  sla_breach: { label: "Past target", tone: "bad" },
  evidence: { label: "Check cleanup", tone: "warn" },
  review: { label: "Review", tone: "neutral" },
  dispatch: { label: "Assign crew", tone: "neutral" },
};

export function AttentionList({ items, selectedId, onSelect }: { items: AttentionItem[]; selectedId: string | null; onSelect: (id: string, item: AttentionItem) => void }) {
  if (items.length === 0) {
    return (
      <div className="empty" style={{ padding: "28px 12px" }}>
        <h3>Nothing needs you right now</h3>
        <p>New items appear here as reports come in, cleanups finish or deadlines near.</p>
      </div>
    );
  }
  return (
    <ul className="attention">
      {items.map((a) => {
        const k = KIND[a.kind];
        return (
          <li key={a.incident.id + a.kind}>
            <button type="button" className="attention-row" aria-pressed={selectedId === a.incident.id} onClick={() => onSelect(a.incident.id, a)}>
              <ShapeGlyph status={a.incident.status} size={18} />
              <span className="attention-main">
                <span className="attention-title">{a.incident.description}</span>
                <span className="attention-meta">
                  <span className="tone" data-tone={k.tone}>
                    {k.label}
                  </span>
                  {a.reason}
                  {a.severity ? ` · ${a.severity}` : ""}
                </span>
              </span>
            </button>
            <Link href={`/incidents/${a.incident.id}`} className="attention-open" aria-label={`Open report: ${a.incident.description}`}>
              Open
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

/* ------------------------------------------------------------------ hotspots + crews */

export function HotspotList({ hotspots, onShow }: { hotspots: DashboardSummary["hotspots"]; onShow: (lat: number, lon: number) => void }) {
  if (hotspots.length === 0) return <p className="muted">No place has been reported three or more times in 90 days.</p>;
  return (
    <ul className="hotspots">
      {hotspots.map((h, i) => (
        <li key={i}>
          <span className="count-badge" title={`${h.reports_90d} reports in 90 days`}>
            {h.reports_90d}
          </span>
          <div>
            <Link href={`/incidents/${h.incident_id}`} className="hotspot-title">
              {h.sample}
            </Link>
            <span className="muted">
              {h.open > 0 ? `${h.open} open` : "none open"} · last {formatWhen(h.last_reported)}
            </span>
          </div>
          <button type="button" className="btn btn-quiet" onClick={() => onShow(h.latitude, h.longitude)}>
            Show on map
          </button>
        </li>
      ))}
    </ul>
  );
}

export function Workload({ workload }: { workload: DashboardSummary["workload"] }) {
  if (workload.length === 0) return <p className="muted">No active crew accounts yet.</p>;
  const max = Math.max(3, ...workload.map((w) => w.active_jobs));
  return (
    <ul className="workload">
      {workload.map((w) => (
        <li key={w.worker_id}>
          <span>{w.name}</span>
          <div className="workload-track" role="img" aria-label={`${w.active_jobs} active jobs, ${w.in_progress} in progress`}>
            <span className="workload-done" style={{ width: `${(w.in_progress / max) * 100}%` }} />
            <span className="workload-queued" style={{ width: `${((w.active_jobs - w.in_progress) / max) * 100}%` }} />
          </div>
          <strong>{w.active_jobs}</strong>
        </li>
      ))}
      <li className="workload-legend muted">
        <span>
          <i className="swatch-box workload-done" /> Being worked
        </span>
        <span>
          <i className="swatch-box workload-queued" /> Assigned
        </span>
      </li>
    </ul>
  );
}
