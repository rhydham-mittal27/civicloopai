"use client";

import Link from "next/link";
import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Empty, ErrorNote, Loading, OrderBadge, PageHead, Spinner, formatWhen, shortId } from "@/components/ui";
import { STAFF } from "@/lib/access";
import { api, ORDER_LABEL, type WorkOrder, type WorkOrderStatus } from "@/lib/api";
import { isSupervisor, useAuth } from "@/lib/auth";
import { useAction, useLoad } from "@/lib/hooks";

const FILTERS: (WorkOrderStatus | "all")[] = ["all", "draft", "approved", "assigned", "in_progress", "completed", "cancelled"];

export default function WorkPage() {
  return (
    <AppShell roles={STAFF}>
      <Work />
    </AppShell>
  );
}

function Work() {
  const { principal } = useAuth();
  const supervisor = isSupervisor(principal?.role);
  const [filter, setFilter] = useState<WorkOrderStatus | "all">("all");
  const { data, error, loading, reload } = useLoad(() => api.listOrders(filter === "all" ? undefined : filter), [filter]);
  const workers = useLoad(() => (supervisor ? api.listUsers("sanitation_worker") : Promise.resolve([])), [supervisor]);
  const { busy, error: actionError, run } = useAction();
  const [pick, setPick] = useState<Record<string, string>>({});

  const act = async (key: string, fn: () => Promise<unknown>, message: string) => {
    if (await run(key, fn, message)) reload();
  };

  const orders: WorkOrder[] = data ?? [];

  return (
    <>
      <PageHead title={supervisor ? "Work orders" : "My assignments"}>
        {supervisor ? "Approve, assign and follow every cleanup job." : "Cleanups assigned to you. Open one to start work and send evidence."}
      </PageHead>

      <div className="tabs" role="tablist" aria-label="Work order status">
        {FILTERS.map((status) => (
          <button key={status} type="button" role="tab" aria-selected={filter === status} className="tab" onClick={() => setFilter(status)}>
            {status === "all" ? "All" : ORDER_LABEL[status]}
          </button>
        ))}
      </div>

      <ErrorNote message={actionError} />
      <div className="table-wrap">
        {error ? (
          <Empty title="Could not load work orders">{error}</Empty>
        ) : loading && !data ? (
          <Loading />
        ) : orders.length === 0 ? (
          <Empty title="No work orders here">
            {supervisor ? "Open a work order from an incident that is ready for review." : "Nothing has been assigned to you yet."}
          </Empty>
        ) : (
          <ul className="rows">
            {orders.map((order, i) => (
              <li key={order.id} className="row row-order" style={{ "--i": Math.min(i, 10) } as React.CSSProperties}>
                <div>
                  <Link href={`/incidents/${order.incident_id}`} className="row-title link-title">
                    {order.incident?.description ?? `Incident ${shortId(order.incident_id)}`}
                  </Link>
                  <div className="row-sub">
                    <span className="mono">order {shortId(order.id)}</span>
                    <span>priority {order.priority}</span>
                    {order.estimated_volume !== null && <span>{order.estimated_volume} m³</span>}
                    <span>{order.assigned_to_name ? `assigned to ${order.assigned_to_name}` : "unassigned"}</span>
                    <span>{formatWhen(order.created_at)}</span>
                  </div>
                </div>
                <OrderBadge status={order.status} />
                <div className="row-actions">
                  {supervisor && order.status === "draft" && (
                    <button className="btn" disabled={!!busy} onClick={() => act(order.id, () => api.approveOrder(order.id), "Approved")}>
                      {busy === order.id && <Spinner />}
                      Approve
                    </button>
                  )}
                  {supervisor && order.status === "approved" && (
                    <>
                      <label className="sr-only" htmlFor={`worker-${order.id}`}>
                        Assign worker for order {shortId(order.id)}
                      </label>
                      <select id={`worker-${order.id}`} className="select select-sm" value={pick[order.id] ?? ""} onChange={(e) => setPick({ ...pick, [order.id]: e.target.value })}>
                        <option value="">Assign to…</option>
                        {(workers.data ?? []).filter((w) => w.is_active).map((w) => (
                          <option key={w.id} value={w.id}>
                            {w.name}
                          </option>
                        ))}
                      </select>
                      <button className="btn" disabled={!!busy || !pick[order.id]} onClick={() => act(order.id, () => api.assignOrder(order.id, pick[order.id]), "Worker assigned")}>
                        {busy === order.id && <Spinner />}
                        Assign
                      </button>
                    </>
                  )}
                  {!supervisor && order.status === "assigned" && (
                    <button className="btn btn-primary" disabled={!!busy} onClick={() => act(order.id, () => api.startOrder(order.id), "Work started")}>
                      {busy === order.id && <Spinner />}
                      Start
                    </button>
                  )}
                  {!supervisor && (order.status === "assigned" || order.status === "in_progress") && (
                    <button className="btn" disabled={!!busy} onClick={() => act(order.id, () => api.completeOrder(order.id), "Marked complete")}>
                      Complete
                    </button>
                  )}
                  {!supervisor && order.status === "completed" && (
                    <Link href={`/incidents/${order.incident_id}`} className="btn btn-primary">
                      Send evidence
                    </Link>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}
