"use client";

import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { ErrorNote, Loading, PageHead, Spinner, formatWhen, shortId } from "@/components/ui";
import { SUPERVISORS } from "@/lib/access";
import { api, ORDER_LABEL, type WorkOrderStatus } from "@/lib/api";
import { useAction, useLoad } from "@/lib/hooks";

export default function IntegrationsPage() {
  return (
    <AppShell roles={SUPERVISORS}>
      <Integrations />
    </AppShell>
  );
}

function Integrations() {
  const [tab, setTab] = useState<"sensors" | "municipal">("sensors");
  return (
    <>
      <PageHead title="Integrations">Bring in bin sensors and exchange work orders with the municipal system.</PageHead>
      <div className="tabs" role="tablist" aria-label="Integrations">
        {(["sensors", "municipal"] as const).map((t) => (
          <button key={t} type="button" role="tab" aria-selected={tab === t} className="tab" onClick={() => setTab(t)}>
            {t === "sensors" ? "IoT sensors" : "Municipal system"}
          </button>
        ))}
      </div>
      {tab === "sensors" ? <Sensors /> : <Municipal />}
    </>
  );
}

function Sensors() {
  const readings = useLoad(() => api.recentReadings(), []);
  const { busy, error, run } = useAction();
  const [form, setForm] = useState({ sensor_id: "", latitude: "", longitude: "", metric: "fill_level", value: "" });
  const [lookup, setLookup] = useState("");
  const [found, setFound] = useState<string | null>(null);
  const [link, setLink] = useState<Record<string, string>>({});
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  return (
    <>
      <form
        className="form form-wide"
        onSubmit={async (e) => {
          e.preventDefault();
          const value = Number.isFinite(Number(form.value)) ? Number(form.value) : form.value;
          const done = await run(
            "ingest",
            () =>
              api.ingestReading({
                sensor_id: form.sensor_id.trim(),
                latitude: Number(form.latitude),
                longitude: Number(form.longitude),
                reading: { [form.metric.trim()]: value },
              }),
            "Reading recorded",
          );
          if (done) {
            setForm({ ...form, value: "" });
            readings.reload();
          }
        }}
      >
        <h2 className="h-sm">Record a reading</h2>
        <div className="split">
          <div className="field">
            <label htmlFor="s-id">Sensor ID</label>
            <input id="s-id" className="input" required value={form.sensor_id} onChange={set("sensor_id")} placeholder="bin-sector17-04" />
          </div>
          <div className="field">
            <label htmlFor="s-metric">Measurement</label>
            <input id="s-metric" className="input" required value={form.metric} onChange={set("metric")} />
          </div>
          <div className="field">
            <label htmlFor="s-lat">Latitude</label>
            <input id="s-lat" className="input mono" required inputMode="decimal" value={form.latitude} onChange={set("latitude")} />
          </div>
          <div className="field">
            <label htmlFor="s-lon">Longitude</label>
            <input id="s-lon" className="input mono" required inputMode="decimal" value={form.longitude} onChange={set("longitude")} />
          </div>
        </div>
        <div className="field">
          <label htmlFor="s-val">Value</label>
          <input id="s-val" className="input" required value={form.value} onChange={set("value")} placeholder="0.85" />
        </div>
        <div>
          <button className="btn btn-primary" disabled={!!busy}>
            {busy === "ingest" && <Spinner />}
            Record reading
          </button>
        </div>
      </form>

      <form
        className="inline-form"
        onSubmit={async (e) => {
          e.preventDefault();
          const r = await run("lookup", () => api.latestReading(lookup.trim()));
          setFound(r ? `${r.sensor_id}: ${Object.entries(r.reading).map(([k, v]) => `${k} ${String(v)}`).join(", ")} at ${formatWhen(r.observed_at)}` : null);
        }}
      >
        <div className="field grow">
          <label htmlFor="s-look">Latest reading for a sensor</label>
          <input id="s-look" className="input" value={lookup} onChange={(e) => setLookup(e.target.value)} placeholder="Sensor ID" />
        </div>
        <button className="btn" disabled={!!busy || !lookup.trim()}>
          Look up
        </button>
      </form>
      {found && <p className="verdict">{found}</p>}
      <ErrorNote message={error} />

      <section className="section" aria-labelledby="recent">
        <h2 id="recent">Recent readings</h2>
        {readings.loading && !readings.data ? (
          <Loading />
        ) : (readings.data ?? []).length === 0 ? (
          <p className="muted">No readings recorded yet.</p>
        ) : (
          <div className="table-wrap">
          <table className="tbl">
            <thead>
              <tr>
                <th>Sensor</th>
                <th>Reading</th>
                <th>Where</th>
                <th>When</th>
                <th>Incident</th>
              </tr>
            </thead>
            <tbody>
              {(readings.data ?? []).map((r) => (
                <tr key={r.id}>
                  <td>{r.sensor_id}</td>
                  <td className="mono">{Object.entries(r.reading).map(([k, v]) => `${k} ${String(v)}`).join(", ")}</td>
                  <td className="mono">
                    {r.latitude.toFixed(4)}, {r.longitude.toFixed(4)}
                  </td>
                  <td>{formatWhen(r.observed_at)}</td>
                  <td>
                    {r.incident_id ? (
                      <span className="tag">#{shortId(r.incident_id)}</span>
                    ) : (
                      <span className="inline-form tight">
                        <input
                          className="input select-sm mono"
                          aria-label={`Incident ID to link ${r.sensor_id}`}
                          placeholder="incident id"
                          value={link[r.id] ?? ""}
                          onChange={(e) => setLink({ ...link, [r.id]: e.target.value })}
                        />
                        <button
                          className="btn"
                          disabled={!!busy || !link[r.id]}
                          onClick={async () => {
                            if (await run(r.id, () => api.associateReading(r.id, link[r.id].trim()), "Sensor linked")) readings.reload();
                          }}
                        >
                          Link
                        </button>
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </section>
    </>
  );
}

function Municipal() {
  const orders = useLoad(() => api.listOrders(), []);
  const { busy, error, run } = useAction();
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [system, setSystem] = useState("ward-office");
  const [exported, setExported] = useState<string | null>(null);
  const [updates, setUpdates] = useState<Record<string, WorkOrderStatus | "">>({});
  const [result, setResult] = useState<string | null>(null);

  const toggle = (id: string) =>
    setPicked((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const pending = Object.entries(updates).filter(([, s]) => s !== "") as [string, WorkOrderStatus][];

  return (
    <>
      <div className="field form-wide">
        <label htmlFor="m-sys">System name</label>
        <input id="m-sys" className="input" value={system} onChange={(e) => setSystem(e.target.value)} />
        <span className="hint">No external system is connected, so exports download as a file and imports are applied from this page.</span>
      </div>
      <ErrorNote message={error} />

      {orders.loading && !orders.data ? (
        <Loading />
      ) : (orders.data ?? []).length === 0 ? (
        <p className="muted">There are no work orders to exchange yet.</p>
      ) : (
        <div className="table-wrap" style={{ marginTop: 16 }}>
          <table className="tbl">
            <thead>
              <tr>
                <th>
                  <span className="sr-only">Select</span>
                </th>
                <th>Work order</th>
                <th>Status</th>
                <th>Update from municipal system</th>
              </tr>
            </thead>
            <tbody>
              {(orders.data ?? []).map((o) => (
                <tr key={o.id}>
                  <td>
                    <input type="checkbox" aria-label={`Export order ${shortId(o.id)}`} checked={picked.has(o.id)} onChange={() => toggle(o.id)} />
                  </td>
                  <td>
                    {o.incident?.description ?? shortId(o.incident_id)}
                    <div className="muted mono">{shortId(o.id)}</div>
                  </td>
                  <td>{ORDER_LABEL[o.status]}</td>
                  <td>
                    <select className="select select-sm" aria-label={`New status for order ${shortId(o.id)}`} value={updates[o.id] ?? ""} onChange={(e) => setUpdates({ ...updates, [o.id]: e.target.value as WorkOrderStatus | "" })}>
                      <option value="">No change</option>
                      {(Object.keys(ORDER_LABEL) as WorkOrderStatus[]).filter((s) => s !== o.status).map((s) => (
                        <option key={s} value={s}>
                          {ORDER_LABEL[s]}
                        </option>
                      ))}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="btn-row" style={{ marginTop: 16 }}>
        <button
          className="btn btn-primary"
          disabled={!!busy || picked.size === 0}
          onClick={async () => {
            const out = await run("export", () => api.municipalExport([...picked], system.trim() || "municipal"), "Export ready");
            setExported(out ? JSON.stringify(out, null, 2) : null);
          }}
        >
          {busy === "export" && <Spinner />}
          Export {picked.size || ""} selected
        </button>
        <button
          className="btn"
          disabled={!!busy || pending.length === 0}
          onClick={async () => {
            const out = await run("import", () => api.municipalImport(pending.map(([work_order_id, status]) => ({ work_order_id, status })), system.trim() || "municipal"));
            if (out) {
              setResult(`Applied ${out.imported} of ${out.received} updates.`);
              setUpdates({});
              orders.reload();
            }
          }}
        >
          {busy === "import" && <Spinner />}
          Apply {pending.length || ""} status updates
        </button>
      </div>
      {result && <p className="verdict">{result}</p>}
      {exported && (
        <section className="section" aria-labelledby="export-out">
          <h2 id="export-out">Export payload</h2>
          <pre className="code">{exported}</pre>
          <div>
            <a className="btn" download="civicloop-work-orders.json" href={`data:application/json;charset=utf-8,${encodeURIComponent(exported)}`}>
              Download JSON
            </a>
          </div>
        </section>
      )}
    </>
  );
}
