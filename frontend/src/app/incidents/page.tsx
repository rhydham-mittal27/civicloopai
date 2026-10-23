"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { ShapeGlyph } from "@/components/map/SightingsMap";
import { Empty, Icon, PageHead, RiskBar, StatusBadge } from "@/components/ui";
import { api, type Incident, type IncidentStatus, type MapPoint, type Risk } from "@/lib/api";
import { isSupervisor, useAuth } from "@/lib/auth";
import { useLoad } from "@/lib/hooks";
import { STATUS_STYLE } from "@/lib/status";

type Row = { incident: Incident; risk: Risk | null };
type TabKey = "pending_analysis" | "ready_for_review" | "approved" | "in_progress" | "uncertain" | "closed";
type Sort = "risk" | "newest" | "oldest";

const TABS: { key: TabKey; label: string; statuses: IncidentStatus[] }[] = [
  { key: "pending_analysis", label: "Pending analysis", statuses: ["pending_analysis"] },
  { key: "ready_for_review", label: "Ready for review", statuses: ["ready_for_review"] },
  { key: "approved", label: "Approved", statuses: ["approved"] },
  { key: "in_progress", label: "In progress", statuses: ["in_progress"] },
  { key: "uncertain", label: "Needs a decision", statuses: ["uncertain"] },
  { key: "closed", label: "Closed", statuses: ["resolved", "verified", "rejected"] },
];

export function timeAgo(iso: string, now = Date.now()): string {
  const hours = (now - new Date(iso).getTime()) / 3_600_000;
  if (hours < 1) return "just now";
  if (hours < 48) return `${Math.round(hours)} h ago`;
  return `${Math.round(hours / 24)} days ago`;
}

export default function IncidentsPage() {
  return (
    <AppShell>
      <Incidents />
    </AppShell>
  );
}

function Incidents() {
  const { principal } = useAuth();
  const ranked = isSupervisor(principal?.role);
  const reporter = principal?.role === "reporter";
  const [chosen, setChosen] = useState<TabKey | null>(null);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<Sort | null>(null);

  const { data, error, loading, reload } = useLoad(async () => {
    const statuses = TABS.flatMap((t) => t.statuses);
    const lists = await Promise.all(
      statuses.map(async (status): Promise<[IncidentStatus, Row[]]> => {
        if (ranked && status === "ready_for_review") return [status, await api.queue(status)];
        return [status, (await api.listIncidents(status)).map((incident) => ({ incident, risk: null }))];
      }),
    );
    const extra: MapPoint[] = ranked ? await api.dashboardMap().catch(() => []) : [];
    return { byStatus: Object.fromEntries(lists) as Record<IncidentStatus, Row[]>, extra: new Map(extra.map((p) => [p.id, p])) };
  }, [ranked]);

  const rowsFor = (tab: TabKey): Row[] => TABS.find((t) => t.key === tab)!.statuses.flatMap((s) => data?.byStatus[s] ?? []);
  const first = !data;

  // until the user picks a tab, show the most useful non-empty one
  const preferred: TabKey[] = ranked ? ["ready_for_review", "pending_analysis", "approved", "in_progress", "uncertain", "closed"] : ["pending_analysis", "ready_for_review", "approved", "in_progress", "uncertain", "closed"];
  const active: TabKey = chosen ?? preferred.find((t) => rowsFor(t).length > 0) ?? "ready_for_review";
  const effectiveSort: Sort = sort ?? (ranked && active === "ready_for_review" ? "risk" : "newest");

  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const list = (data ? TABS.find((t) => t.key === active)!.statuses.flatMap((s) => data.byStatus[s] ?? []) : []).filter(
      (r) => !needle || r.incident.description.toLowerCase().includes(needle) || r.incident.id.startsWith(needle),
    );
    const time = (r: Row) => new Date(r.incident.occurred_at).getTime();
    return list.sort((a, b) => (effectiveSort === "risk" ? (b.risk?.score ?? -1) - (a.risk?.score ?? -1) || time(b) - time(a) : effectiveSort === "oldest" ? time(a) - time(b) : time(b) - time(a)));
  }, [data, active, query, effectiveSort]);

  return (
    <>
      <PageHead
        title={reporter ? "My reports" : "Incidents"}
        actions={
          <Link href="/incidents/new" className="btn btn-primary">
            <Icon name="plus" />
            Report incident
          </Link>
        }
      >
        {reporter ? "Every report you have filed and where it stands." : "Every report, by where it is in the cleanup loop."}
      </PageHead>

      <div className="tabs tabs-fit" role="tablist" aria-label="Incident status">
        {TABS.map((tab) => {
          const count = first ? "–" : rowsFor(tab.key).length;
          return (
            <button key={tab.key} type="button" role="tab" id={`tab-${tab.key}`} aria-selected={active === tab.key} aria-controls="queue-panel" className="tab" onClick={() => setChosen(tab.key)}>
              {tab.key !== "closed" && <ShapeGlyph status={tab.statuses[0]} size={15} />}
              {tab.label}
              <span className="count">{count}</span>
            </button>
          );
        })}
      </div>

      <div className="list-tools">
        <label className="search">
          <Icon name="search" />
          <span className="sr-only">Search reports</span>
          <input type="search" placeholder="Search by description or ID" value={query} onChange={(e) => setQuery(e.target.value)} />
        </label>
        <label className="sort">
          <span>Sort</span>
          <select className="select select-sm" value={effectiveSort} onChange={(e) => setSort(e.target.value as Sort)}>
            {ranked && <option value="risk">Highest risk</option>}
            <option value="newest">Newest first</option>
            <option value="oldest">Oldest first</option>
          </select>
        </label>
        <span className="muted list-count">{first ? "" : `${rows.length} ${rows.length === 1 ? "report" : "reports"}`}</span>
      </div>

      <div id="queue-panel" role="tabpanel" aria-labelledby={`tab-${active}`} className="ilist">
        {error && first ? (
          <Empty
            title="Could not load incidents"
            action={
              <button type="button" className="btn" onClick={reload}>
                Try again
              </button>
            }
          >
            {error}
          </Empty>
        ) : loading && first ? (
          <div aria-busy="true" aria-label="Loading incidents">
            {[0, 1, 2, 3, 4].map((i) => (
              <div key={i} className="skeleton" />
            ))}
          </div>
        ) : rows.length === 0 ? (
          <Empty title={query ? "No reports match your search" : `Nothing ${TABS.find((t) => t.key === active)!.label.toLowerCase()}`}>
            {query ? "Try a different word, or clear the search." : active === "ready_for_review" ? "New reports show up here once the AI has analysed them." : "Reports appear here when they reach this stage."}
          </Empty>
        ) : (
          <>
            <div className="ilist-head" aria-hidden="true">
              <span>Report</span>
              {ranked && <span>Risk</span>}
              <span>Severity</span>
              <span>Waiting</span>
            </div>
            <ul key={active + effectiveSort}>
              {rows.map(({ incident, risk }, i) => {
                const extra = data?.extra.get(incident.id);
                const style = STATUS_STYLE[incident.status];
                return (
                  <li key={incident.id}>
                    <Link href={`/incidents/${incident.id}`} className="irow" data-ranked={ranked ? "" : undefined} style={{ "--i": Math.min(i, 12) } as React.CSSProperties}>
                      <span className="irow-main">
                        <ShapeGlyph status={incident.status} size={18} />
                        <span className="sr-only">{style.label}: </span>
                        <span className="irow-text">
                          <span className="irow-title">{incident.description}</span>
                          <span className="irow-meta">
                            <span className="mono">#{incident.id.slice(0, 8)}</span>
                            <span>{incident.reporter_type.replace("_", " ")}</span>
                            {active === "closed" && <StatusBadge status={incident.status} />}
                            {extra?.breached && <span className="flag">Past target</span>}
                          </span>
                        </span>
                      </span>
                      {ranked && <span className="irow-risk">{risk ? <RiskBar score={risk.score} probability={risk.kind === "probability"} /> : <span className="muted">–</span>}</span>}
                      <span className="irow-sev" data-level={extra?.severity ?? "none"}>
                        {extra?.severity ?? "–"}
                      </span>
                      <span className="irow-age" title={new Date(incident.occurred_at).toLocaleString()}>
                        {timeAgo(incident.occurred_at)}
                      </span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </div>
    </>
  );
}
