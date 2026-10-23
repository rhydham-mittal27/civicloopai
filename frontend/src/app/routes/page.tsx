"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { KpiCard } from "@/components/dashboard/widgets";
import { AppShell } from "@/components/AppShell";
import { PlannerMap, type Job } from "@/components/map/PlannerMap";
import { Empty, ErrorNote, Loading, PageHead, Spinner, formatWhen, pct, shortId } from "@/components/ui";
import { SUPERVISORS } from "@/lib/access";
import { api, type RoutePlan } from "@/lib/api";
import { useAction, useLoad } from "@/lib/hooks";

export default function RoutesPage() {
  return (
    <AppShell roles={SUPERVISORS}>
      <Planner />
    </AppShell>
  );
}

const CITY_CENTRE = { lat: "30.7333", lon: "76.7794" };

function Planner() {
  const router = useRouter();
  const orders = useLoad(async () => [...(await api.listOrders("approved")), ...(await api.listOrders("assigned"))], []);
  const plans = useLoad(() => api.listRoutes(), []);
  const { busy, error, run } = useAction();

  const [selected, setSelected] = useState<string[]>([]); // click order is the "selection order" baseline
  const [capacity, setCapacity] = useState("20");
  const [maxMinutes, setMaxMinutes] = useState("");
  const [depotOn, setDepotOn] = useState(true);
  const [depot, setDepot] = useState(CITY_CENTRE);
  const [compare, setCompare] = useState(true);
  const [showExisting, setShowExisting] = useState(false);
  const [preview, setPreview] = useState<{ key: string; plan: RoutePlan } | null>(null);

  const routed = useMemo(() => new Set((plans.data ?? []).flatMap((p) => p.stops.map((s) => s.work_order_id))), [plans.data]);
  const jobs: Job[] = useMemo(
    () =>
      (orders.data ?? [])
        .filter((o) => !routed.has(o.id) && o.incident)
        .map((o) => ({ id: o.id, lat: o.incident!.latitude, lon: o.incident!.longitude, priority: o.priority, volume: o.estimated_volume ?? 0, label: o.incident!.description }))
        .sort((a, b) => b.priority - a.priority),
    [orders.data, routed],
  );
  const byId = new Map(jobs.map((j) => [j.id, j]));
  const chosen = selected.filter((id) => byId.has(id));
  const volume = chosen.reduce((sum, id) => sum + (byId.get(id)?.volume ?? 0), 0);
  const cap = Number(capacity) || 0;
  const over = volume > cap;
  const depotPoint = depotOn && Number.isFinite(Number(depot.lat)) && Number.isFinite(Number(depot.lon)) ? { lat: Number(depot.lat), lon: Number(depot.lon) } : null;

  const request = {
    work_order_ids: chosen,
    vehicle_capacity: cap,
    ...(depotPoint ? { depot_latitude: depotPoint.lat, depot_longitude: depotPoint.lon } : {}),
    ...(maxMinutes ? { max_duration_minutes: Number(maxMinutes) } : {}),
  };
  const key = JSON.stringify(request);
  const current = preview && preview.key === key ? preview.plan : null;

  const toggle = (id: string) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const fillVehicle = () => {
    const next: string[] = [];
    let used = 0;
    for (const j of jobs) {
      if (used + j.volume <= cap) {
        next.push(j.id);
        used += j.volume;
      }
    }
    setSelected(next);
  };

  async function doPreview() {
    const plan = await run("preview", () => api.previewRoute(request));
    if (plan) setPreview({ key, plan });
  }
  async function save() {
    const plan = await run("save", () => api.createRoute(request), "Route saved as a draft");
    if (plan) router.push(`/routes/${plan.id}`);
  }

  const all = plans.data ?? [];
  const awaiting = all.filter((p) => !p.approved_by).length;
  const savings = all.map((p) => p.saving_ratio).filter((v): v is number => v !== null);
  const readyVolume = jobs.reduce((s, j) => s + j.volume, 0);

  return (
    <>
      <PageHead title="Route planner">Pick the jobs for one vehicle, preview the optimised route against the order you picked them in, then save it for approval. Nothing is dispatched automatically.</PageHead>

      <section className="kpis kpis-act" aria-label="Dispatch at a glance">
        <KpiCard icon="truck" label="Jobs ready to route" value={jobs.length} secondary={`· ${readyVolume.toFixed(1)} m³`} detail="Approved and not on a route yet" band={jobs.length > 0 ? "warn" : "good"} />
        <KpiCard icon="review" label="Routes to approve" value={awaiting} secondary={`/ ${all.length}`} detail={awaiting ? "Drafts waiting for you" : "Nothing waiting"} band={awaiting > 0 ? "warn" : "good"} hint="Routes that are planned but not yet approved." ring={all.length ? (all.length - awaiting) / all.length : null} />
        <KpiCard icon="route" label="Stops per route" value={all.length ? (all.reduce((s, p) => s + p.stops.length, 0) / all.length).toFixed(1) : "–"} detail={`${all.length} route${all.length === 1 ? "" : "s"} planned`} />
        <KpiCard
          icon="chart"
          label="Saved vs pick order"
          value={savings.length ? pct(savings.reduce((a, b) => a + b, 0) / savings.length) : "–"}
          detail="Average distance saved by optimising"
          ring={savings.length ? Math.max(0, savings.reduce((a, b) => a + b, 0) / savings.length) : null}
         
          hint="Planned distance compared with visiting the same stops in the order they were picked, straight-line."
        />
      </section>

      {orders.loading && !orders.data ? (
        <Loading label="Loading jobs" />
      ) : orders.error ? (
        <ErrorNote message={orders.error} />
      ) : jobs.length === 0 ? (
        <Empty
          title="No jobs are waiting for a route"
          action={
            <Link href="/work" className="btn">
              Approve more work orders
            </Link>
          }
        >
          {routed.size > 0 ? `All ${routed.size} approved jobs are already on a planned route.` : "Approve work orders first, then plan their route here."}
        </Empty>
      ) : (
        <section className="planner" aria-label="Plan a route">
          <div className="planner-left">
            <PlannerMap jobs={jobs} selected={new Set(chosen)} onToggle={toggle} depot={depotPoint} preview={current} compare={compare} existing={all} showExisting={showExisting} />
            <div className="planner-toggles">
              <label className="check">
                <input type="checkbox" checked={showExisting} onChange={(e) => setShowExisting(e.target.checked)} />
                <span>Show planned routes</span>
              </label>
              {current && (
                <label className="check">
                  <input type="checkbox" checked={compare} onChange={(e) => setCompare(e.target.checked)} />
                  <span>Compare with the order I picked (dotted)</span>
                </label>
              )}
            </div>
          </div>

          <aside className="planner-panel" aria-label="Route settings">
            <div className="step">
              <div className="step-head">
                <h2>
                  <span className="step-n">1</span> Pick jobs
                </h2>
                <div className="btn-row">
                  <button type="button" className="btn btn-quiet" onClick={fillVehicle} title="Add the highest-priority jobs until the vehicle is full">
                    Fill vehicle
                  </button>
                  <button type="button" className="btn btn-quiet" onClick={() => setSelected([])} disabled={chosen.length === 0}>
                    Clear
                  </button>
                </div>
              </div>
              <ul className="joblist">
                {jobs.map((j) => {
                  const on = chosen.includes(j.id);
                  return (
                    <li key={j.id}>
                      <label className="job" data-on={on ? "" : undefined}>
                        <input type="checkbox" checked={on} onChange={() => toggle(j.id)} />
                        <span className="job-body">
                          <span className="job-title">{j.label}</span>
                          <span className="job-meta">
                            <span className="prio" data-urgent={j.priority >= 70 ? "" : undefined}>
                              Priority {j.priority}
                            </span>
                            {j.volume} m³
                          </span>
                        </span>
                      </label>
                    </li>
                  );
                })}
              </ul>
            </div>

            <div className="step">
              <div className="step-head">
                <h2>
                  <span className="step-n">2</span> Vehicle
                </h2>
              </div>
              <div className="fillbar" role="img" aria-label={`${volume.toFixed(1)} of ${cap} cubic metres used`} data-over={over ? "" : undefined}>
                <span style={{ width: `${Math.min(100, cap ? (volume / cap) * 100 : 0)}%` }} />
              </div>
              <p className="fill-text" data-over={over ? "" : undefined}>
                {chosen.length} job{chosen.length === 1 ? "" : "s"} · {volume.toFixed(1)} of {cap || 0} m³ {over ? "· over capacity" : cap ? `· ${Math.round((volume / cap) * 100)}% full` : ""}
              </p>
              <div className="split">
                <div className="field">
                  <label htmlFor="cap">Capacity (m³)</label>
                  <input id="cap" className="input" type="number" min={0.1} step="0.5" value={capacity} onChange={(e) => setCapacity(e.target.value)} />
                </div>
                <div className="field">
                  <label htmlFor="maxmin">Longest drive (min)</label>
                  <input id="maxmin" className="input" type="number" min={1} max={1440} value={maxMinutes} placeholder="no limit" onChange={(e) => setMaxMinutes(e.target.value)} />
                </div>
              </div>
              <label className="check">
                <input type="checkbox" checked={depotOn} onChange={(e) => setDepotOn(e.target.checked)} />
                <span>Start and end at a depot</span>
              </label>
              {depotOn && (
                <details className="depot-fields">
                  <summary>Depot coordinates</summary>
                  <div className="split">
                    <input className="input mono" aria-label="Depot latitude" inputMode="decimal" value={depot.lat} onChange={(e) => setDepot({ ...depot, lat: e.target.value })} />
                    <input className="input mono" aria-label="Depot longitude" inputMode="decimal" value={depot.lon} onChange={(e) => setDepot({ ...depot, lon: e.target.value })} />
                  </div>
                </details>
              )}
            </div>

            <div className="step">
              <div className="step-head">
                <h2>
                  <span className="step-n">3</span> Preview and save
                </h2>
              </div>
              <ErrorNote message={error} />
              {!current ? (
                <button type="button" className="btn btn-primary btn-block" disabled={!!busy || chosen.length === 0 || over || cap <= 0} onClick={doPreview}>
                  {busy === "preview" && <Spinner />}
                  Preview optimised route
                </button>
              ) : (
                <div className="preview-card">
                  <dl className="preview-stats">
                    <div>
                      <dt>Distance</dt>
                      <dd>{current.estimated_distance_km?.toFixed(1)} km</dd>
                    </div>
                    <div>
                      <dt>Drive time</dt>
                      <dd>~{Math.round(current.estimated_duration_minutes ?? 0)} min</dd>
                    </div>
                    <div>
                      <dt>Vs pick order</dt>
                      <dd className="good">{current.saving_ratio !== null && current.saving_ratio > 0.005 ? `${pct(current.saving_ratio)} shorter` : "same"}</dd>
                    </div>
                  </dl>
                  <p className="hint muted">
                    {current.solver === "ortools" ? "Optimised with OR-Tools." : "Nearest-neighbour order."} Straight-line estimate at 25 km/h; the saved route page shows the real road route.
                  </p>
                  <ol className="preview-stops">
                    {current.stops.map((s) => (
                      <li key={s.work_order_id}>
                        <span className="stop-n">{s.sequence + 1}</span>
                        <span>{s.incident?.description}</span>
                      </li>
                    ))}
                  </ol>
                  <div className="btn-row">
                    <button type="button" className="btn btn-primary" disabled={!!busy} onClick={save}>
                      {busy === "save" && <Spinner />}
                      Save route
                    </button>
                    <button type="button" className="btn" disabled={!!busy} onClick={() => setPreview(null)}>
                      Discard preview
                    </button>
                  </div>
                </div>
              )}
              {over && (
                <p className="fill-text" data-over="">
                  Remove a job or raise the capacity to preview.
                </p>
              )}
            </div>
          </aside>
        </section>
      )}

      <section className="section" aria-labelledby="plans">
        <h2 id="plans">Planned routes</h2>
        {plans.error ? (
          <ErrorNote message={plans.error} />
        ) : plans.loading && !plans.data ? (
          <Loading />
        ) : all.length === 0 ? (
          <Empty title="No routes yet">Saved routes will be listed here for approval.</Empty>
        ) : (
          <div className="route-cards">
            {all.map((plan) => {
              const used = plan.stops.reduce((s, st) => s + (st.planned_volume ?? 0), 0);
              return (
                <Link key={plan.id} href={`/routes/${plan.id}`} className="route-card">
                  <div className="route-card-top">
                    <strong>
                      {plan.stops.length} stops · {plan.estimated_distance_km?.toFixed(1)} km
                    </strong>
                    <span className="badge" data-status={plan.approved_by ? "verified" : "ready_for_review"}>
                      {plan.approved_by ? "Approved" : "Awaiting approval"}
                    </span>
                  </div>
                  <div className="fillbar thin" aria-hidden="true">
                    <span style={{ width: `${Math.min(100, (used / plan.vehicle_capacity) * 100)}%` }} />
                  </div>
                  <div className="route-card-meta">
                    <span>
                      {Math.round((used / plan.vehicle_capacity) * 100)}% of {plan.vehicle_capacity} m³
                    </span>
                    <span>{plan.saving_ratio !== null && plan.saving_ratio > 0.005 ? `${pct(plan.saving_ratio)} shorter than pick order` : "optimised"}</span>
                    <span className="mono">{shortId(plan.id)}</span>
                    <span>{formatWhen(plan.created_at)}</span>
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </section>
    </>
  );
}
