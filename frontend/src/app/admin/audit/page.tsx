"use client";

import Link from "next/link";
import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Empty, Loading, PageHead, formatWhen, shortId } from "@/components/ui";
import { SUPERVISORS } from "@/lib/access";
import { api } from "@/lib/api";
import { useLoad } from "@/lib/hooks";

export default function AuditPage() {
  return (
    <AppShell roles={SUPERVISORS}>
      <Audit />
    </AppShell>
  );
}

const TYPES = ["all", "incident", "work_order", "verification", "route_plan", "duplicate_cluster", "user", "evaluation_run", "sensor_reading", "municipal_export"];

function Audit() {
  const [type, setType] = useState("all");
  const { data, error, loading, reload } = useLoad(() => api.audit(type === "all" ? undefined : type), [type]);

  return (
    <>
      <PageHead
        title="Audit log"
        actions={
          <button className="btn" onClick={reload}>
            Refresh
          </button>
        }
      >
        Every decision, who made it and when. Human overrides carry their reason.
      </PageHead>

      <div className="field form-wide" style={{ marginBottom: 20 }}>
        <label htmlFor="audit-type">Show</label>
        <select id="audit-type" className="select" value={type} onChange={(e) => setType(e.target.value)}>
          {TYPES.map((t) => (
            <option key={t} value={t}>
              {t === "all" ? "Everything" : t.replace(/_/g, " ")}
            </option>
          ))}
        </select>
      </div>

      <div className="table-wrap">
        {error ? (
          <Empty title="Could not load the audit log">{error}</Empty>
        ) : loading && !data ? (
          <Loading />
        ) : (data ?? []).length === 0 ? (
          <Empty title="Nothing logged yet" />
        ) : (
          <table className="tbl">
            <thead>
              <tr>
                <th>When</th>
                <th>Who</th>
                <th>Action</th>
                <th>On</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {(data ?? []).map((e) => (
                <tr key={e.id}>
                  <td>{formatWhen(e.created_at)}</td>
                  <td>{e.actor_name}</td>
                  <td>{e.action.replace(/_/g, " ")}</td>
                  <td>
                    {e.entity_type === "incident" ? (
                      <Link href={`/incidents/${e.entity_id}`} className="mono">
                        incident {shortId(e.entity_id)}
                      </Link>
                    ) : (
                      <span className="mono">
                        {e.entity_type.replace(/_/g, " ")} {shortId(e.entity_id)}
                      </span>
                    )}
                  </td>
                  <td className="cell-wrap muted">{Object.keys(e.details).length ? JSON.stringify(e.details) : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
