"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { RouteMap } from "@/components/RouteMap";
import { ErrorNote, Icon, Loading, Spinner, formatWhen, pct, shortId } from "@/components/ui";
import { SUPERVISORS } from "@/lib/access";
import { api } from "@/lib/api";
import { useAction, useLoad } from "@/lib/hooks";

export default function RoutePage() {
  return (
    <AppShell roles={SUPERVISORS}>
      <RouteDetail />
    </AppShell>
  );
}

function RouteDetail() {
  const { id } = useParams<{ id: string }>();
  const { data: plan, error, reload } = useLoad(() => api.getRoute(id), [id]);
  const { busy, error: actionError, run } = useAction();

  if (error && !plan) {
    return (
      <>
        <Link href="/routes" className="back">
          <Icon name="back" />
          Routes
        </Link>
        <h1>Route not found</h1>
        <p className="muted">{error}</p>
      </>
    );
  }
  if (!plan) return <Loading />;

  return (
    <>
      <Link href="/routes" className="back">
        <Icon name="back" />
        Routes
      </Link>
      <div className="page-head">
        <div>
          <h1>Route {shortId(plan.id)}</h1>
          <p>
            {plan.stops.length} stop{plan.stops.length === 1 ? "" : "s"} · built {formatWhen(plan.created_at)}
          </p>
        </div>
        {plan.approved_by ? (
          <span className="badge" data-status="verified">
            Approved
          </span>
        ) : (
          <button
            className="btn btn-primary"
            disabled={!!busy}
            onClick={async () => {
              if (await run("approve", () => api.approveRoute(plan.id), "Route approved")) reload();
            }}
          >
            {busy && <Spinner />}
            Approve route
          </button>
        )}
      </div>
      <ErrorNote message={actionError} />

      <RouteMap plan={plan} />

      <dl className="facts stat-row">
        <div>
          <dt>Drive time</dt>
          <dd>{plan.estimated_duration_minutes?.toFixed(0)} min</dd>
        </div>
        <div>
          <dt>Capacity</dt>
          <dd>{plan.vehicle_capacity} m³</dd>
        </div>
      </dl>

      <section className="section" aria-labelledby="stops">
        <h2 id="stops">Stops in order</h2>
        <ol className="stops">
          {plan.stops.map((stop) => (
            <li key={stop.sequence}>
              <span className="stop-n">{stop.sequence + 1}</span>
              <div>
                {stop.incident ? <Link href={`/incidents/${stop.incident.id}`}>{stop.incident.description}</Link> : <span className="mono">order {shortId(stop.work_order_id)}</span>}
                <div className="row-sub">
                  {stop.incident && (
                    <span className="mono">
                      {stop.incident.latitude.toFixed(4)}, {stop.incident.longitude.toFixed(4)}
                    </span>
                  )}
                  <span>{stop.planned_volume ?? 0} m³</span>
                </div>
              </div>
            </li>
          ))}
        </ol>
        <p className="hint muted">
          {plan.solver === "ortools"
            ? `Optimised with Google OR-Tools (guided local search). Urgent stops are pulled earlier${plan.saving_vs_greedy === null ? "" : plan.saving_vs_greedy >= 0.005 ? `, ${pct(plan.saving_vs_greedy)} shorter than the nearest-neighbour route` : plan.saving_vs_greedy <= -0.005 ? `, ${pct(-plan.saving_vs_greedy)} longer than the nearest-neighbour route as the price of serving urgent stops sooner` : ", about the same length as the nearest-neighbour route"}.`
            : "Planned with nearest-neighbour ordering."}{" "}
          {plan.max_duration_minutes ? `Limited to ${plan.max_duration_minutes} min of driving. ` : ""}
          Straight-line distances ({plan.engine_version}); road routing is not connected.
        </p>
      </section>
    </>
  );
}
