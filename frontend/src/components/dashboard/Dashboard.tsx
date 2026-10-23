"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type AttentionItem } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import { SightingsMap } from "../map/SightingsMap";
import { Empty, ErrorNote, Icon, Loading, PageHead, formatWhen, pct } from "../ui";
import { AgingChart, AttentionList, FlowChart, HotspotList, KpiCard, Workload, hours, type Band } from "./widgets";

export function Dashboard() {
  const summary = useLoad(() => api.dashboardSummary(14), []);
  const map = useLoad(() => api.dashboardMap(), []);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [focus, setFocus] = useState<{ lat: number; lon: number; stamp: number } | null>(null);
  const reloadSummary = summary.reload;
  const reloadMap = map.reload;

  // an operations screen should stay fresh without anyone pressing a button
  useEffect(() => {
    const timer = setInterval(() => {
      reloadSummary();
      reloadMap();
    }, 60_000);
    return () => clearInterval(timer);
  }, [reloadSummary, reloadMap]);

  if (summary.error && !summary.data) {
    return (
      <>
        <PageHead title="Command center" />
        <ErrorNote message={summary.error} />
      </>
    );
  }
  if (!summary.data) return <Loading label="Loading the dashboard" />;

  const s = summary.data;
  const k = s.kpis;
  const sla = s.sla_hours;

  const reviewBand: Band = k.needs_review.count === 0 ? "good" : k.needs_review.oldest_hours > 24 ? "bad" : k.needs_review.oldest_hours > 8 ? "warn" : "good";
  const slaBand: Band = k.sla.breached === 0 ? "good" : (k.sla.on_time_pct_30d ?? 0) >= 0.9 ? "warn" : "bad";
  const dispatchBand: Band = k.dispatch.unassigned_orders === 0 && k.dispatch.routes_awaiting_approval === 0 ? "good" : k.dispatch.unassigned_orders > 5 ? "bad" : "warn";
  const closureBand: Band = k.verified_closure_rate_30d === null ? "neutral" : k.verified_closure_rate_30d >= 0.85 ? "good" : k.verified_closure_rate_30d >= 0.75 ? "warn" : "bad";

  const select = (id: string | null, item?: AttentionItem) => {
    setSelectedId(id);
    if (item) setFocus({ lat: item.incident.latitude, lon: item.incident.longitude, stamp: Date.now() });
  };

  return (
    <>
      <PageHead
        title="Command center"
        actions={
          <div className="btn-row">
            <button
              type="button"
              className="btn"
              onClick={() => {
                summary.reload();
                map.reload();
              }}
            >
              <Icon name="replay" />
              Refresh
            </button>
            <Link href="/routes" className="btn btn-primary">
              <Icon name="route" />
              Plan routes
            </Link>
          </div>
        }
      >
        Updated {formatWhen(s.generated_at)}. Targets: critical {sla.critical} h, high {sla.high} h, medium {sla.medium} h, low {sla.low} h.
      </PageHead>

      <section className="kpis kpis-row" aria-label="Key numbers">
        <KpiCard
          icon="review"
          label="Needs your review"
          value={k.needs_review.count}
          detail={k.needs_review.count ? `Oldest has waited ${hours(k.needs_review.oldest_hours)}` : "The queue is clear"}
          band={reviewBand}
          href="/incidents"
          ring={k.needs_review.count ? k.needs_review.within_target_pct : null}
          hint="Reports the AI has analysed that are waiting for a supervisor decision. The ring is the share still inside their target time. Turns amber after 8 h and red after 24 h of waiting."
        />
        <KpiCard
          icon="alarm"
          label="Past their target time"
          value={k.sla.breached}
          secondary={`/ ${k.sla.open}`}
          detail={`${k.sla.open} open · ${k.sla.at_risk} at risk · ${k.sla.on_time_pct_30d === null ? "no closures yet" : `${pct(k.sla.on_time_pct_30d)} on time (30 d)`}`}
          band={slaBand}
          ring={k.sla.on_time_pct_30d}
          hint="Open reports older than their severity's target (critical 12 h, high 24 h, medium 48 h, low 72 h). At risk means past 75% of the target. 90% on time is the commonly used goal."
        />
        <KpiCard
          icon="truck"
          label="Awaiting dispatch"
          value={k.dispatch.unassigned_orders}
          secondary={`/ ${k.dispatch.unassigned_orders + k.in_field.jobs}`}
          detail={`of ${k.dispatch.unassigned_orders + k.in_field.jobs} approved jobs · ${k.dispatch.routes_awaiting_approval} route${k.dispatch.routes_awaiting_approval === 1 ? "" : "s"} to approve`}
          band={dispatchBand}
          href="/routes"
          ring={k.dispatch.unassigned_orders + k.in_field.jobs > 0 ? k.in_field.jobs / (k.dispatch.unassigned_orders + k.in_field.jobs) : null}
          hint="Approved jobs that have no crew assigned, plus routes drafted but not yet approved. The ring is the share of approved jobs already with a crew."
        />
        <KpiCard
          icon="users"
          label="In the field"
          value={k.in_field.jobs}
          secondary={`· ${k.in_field.in_progress} live`}
          detail={`${k.evidence_to_review} cleanup${k.evidence_to_review === 1 ? "" : "s"} to check`}
          band={k.evidence_to_review > 0 ? "warn" : "neutral"}
          href="/work"
          ring={k.in_field.jobs ? k.in_field.in_progress / k.in_field.jobs : null}
          hint="Jobs assigned to a crew. The ring is the share already being worked. Cleanups to check are after-photos the rule could not clear on its own."
        />
        <KpiCard
          icon="shield"
          label="Verified closure"
          value={k.verified_closure_rate_30d === null ? "–" : pct(k.verified_closure_rate_30d)}
          detail={k.median_hours_to_close_30d === null ? "Cleanups confirmed ÷ done" : `Median ${hours(k.median_hours_to_close_30d)} to close · ${pct(k.verified_within_24h_pct_30d)} in a day`}
          band={closureBand}
          ring={k.verified_closure_rate_30d}
          hint="Of reports finished in the last 30 days, the share confirmed with evidence. 75 to 85% is the usual field-service range for fixing a job first time. The median is how long a verified report took from filing to closure."
        />
      </section>

      <section className="split-view" aria-label="Sightings">
        <div className="card-plain">
          <div className="card-head">
            <h2>Sightings</h2>
            <span className="muted">{map.data ? `${map.data.length} on the map` : ""}</span>
          </div>
          {map.error && !map.data ? <ErrorNote message={map.error} /> : map.data ? <SightingsMap points={map.data} selectedId={selectedId} onSelect={(id) => select(id)} hotspots={s.hotspots} focus={focus} /> : <Loading label="Loading the map" />}
        </div>
        <div className="card-plain attention-card">
          <div className="card-head">
            <h2>Needs attention</h2>
            <span className="muted">{s.attention.length ? `Top ${s.attention.length}` : ""}</span>
          </div>
          <AttentionList items={s.attention} selectedId={selectedId} onSelect={select} />
        </div>
      </section>

      <section className="duo">
        <div className="card-plain">
          <div className="card-head">
            <h2>Received and closed, 14 days</h2>
          </div>
          <FlowChart flow={s.flow} />
        </div>
        <div className="card-plain">
          <div className="card-head">
            <h2>How long open reports have waited</h2>
          </div>
          <AgingChart aging={s.aging} />
        </div>
      </section>

      <section className="duo">
        <div className="card-plain">
          <div className="card-head">
            <h2>Repeat sites</h2>
            <span className="muted">3+ reports within 500 m, 90 days</span>
          </div>
          <HotspotList
            hotspots={s.hotspots}
            onShow={(lat, lon) => {
              setFocus({ lat, lon, stamp: Date.now() });
              document.querySelector(".sightings")?.scrollIntoView({ behavior: "smooth", block: "center" });
            }}
          />
        </div>
        <div className="card-plain">
          <div className="card-head">
            <h2>Crews</h2>
            <Link href="/work" className="btn btn-quiet">
              Work orders
            </Link>
          </div>
          <Workload workload={s.workload} />
        </div>
      </section>

      {Object.keys(s.counts).length === 0 && (
        <Empty title="No open reports">When residents report sightings they appear here.</Empty>
      )}

      <details className="definitions">
        <summary>How these numbers are counted</summary>
        <ul>
          <li>Open means not yet resolved, verified or rejected. Age counts from when the report was filed.</li>
          <li>Target times are pilot defaults and can be changed in the service; cities set their own (12 hours to a week by complaint type).</li>
          <li>Closed on time compares report-to-closure time with the target for that report&apos;s severity.</li>
          <li>Verified closure is verified reports ÷ (verified + resolved) over 30 days. Time to close is report to last status change on verified reports.</li>
          <li>Simulated training history is never counted.</li>
        </ul>
      </details>
    </>
  );
}
