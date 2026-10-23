"use client";

import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { FleetMap, STATE_LABEL } from "@/components/map/FleetMap";
import { useToast } from "@/components/Toast";
import { Empty, ErrorNote, Icon, Loading, PageHead, Spinner } from "@/components/ui";
import { SUPERVISORS } from "@/lib/access";
import { api, type Vehicle, type VehicleState, type VehicleWithKey } from "@/lib/api";
import { useAction, useLoad } from "@/lib/hooks";

const POLL_MS = 5000;
const ORDER: Record<VehicleState, number> = { moving: 0, idle: 1, stale: 2, offline: 3, no_signal: 4, disabled: 5 };

export default function FleetPage() {
  return (
    <AppShell roles={SUPERVISORS}>
      <Fleet />
    </AppShell>
  );
}

function ago(seconds: number | null): string {
  if (seconds === null) return "never";
  if (seconds < 8) return "just now";
  if (seconds < 90) return `${seconds} s ago`;
  if (seconds < 5400) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 172800) return `${Math.round(seconds / 3600)} h ago`;
  return `${Math.round(seconds / 86400)} days ago`;
}

function Fleet() {
  const toast = useToast();
  const vehicles = useLoad(() => api.vehicles(), []);
  const sightings = useLoad(() => api.dashboardMap(), []);
  const workers = useLoad(() => api.listUsers("sanitation_worker"), []);
  const { busy, error: actionError, run } = useAction();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [focus, setFocus] = useState<{ lat: number; lon: number; stamp: number } | null>(null);
  const [tick, setTick] = useState(0);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ label: "", registration: "", driver_id: "" });
  const [revealed, setRevealed] = useState<VehicleWithKey | null>(null);
  const [confirmKey, setConfirmKey] = useState(false);

  const reloadVehicles = vehicles.reload;
  // The positions refresh every few seconds, but only while this tab is on screen.
  useEffect(() => {
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") {
        reloadVehicles();
        setTick((n) => n + 1);
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [reloadVehicles]);

  const list = useMemo(() => [...(vehicles.data ?? [])].sort((a, b) => ORDER[a.state] - ORDER[b.state] || a.label.localeCompare(b.label)), [vehicles.data]);
  const selected = list.find((v) => v.id === selectedId) ?? null;
  const trail = useLoad(() => (selectedId ? api.vehicleTrail(selectedId, 60) : Promise.resolve([])), [selectedId, Math.floor(tick / 2)]);

  const counts = useMemo(() => {
    const c = { moving: 0, idle: 0, quiet: 0, none: 0, km: 0 };
    list.forEach((v) => {
      if (v.state === "moving") c.moving++;
      else if (v.state === "idle") c.idle++;
      else if (v.state === "stale" || v.state === "offline") c.quiet++;
      else if (v.state === "no_signal") c.none++;
      c.km += v.distance_today_km;
    });
    return c;
  }, [list]);

  const pick = (v: Vehicle) => {
    setSelectedId(v.id === selectedId ? null : v.id);
    setConfirmKey(false);
    if (v.lat !== null && v.lon !== null && v.id !== selectedId) setFocus((f) => ({ lat: v.lat as number, lon: v.lon as number, stamp: (f?.stamp ?? 0) + 1 }));
  };

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    const made = await run("create", () => api.createVehicle({ label: form.label.trim(), registration: form.registration.trim() || undefined, driver_id: form.driver_id || undefined }), "Vehicle added");
    if (made) {
      setRevealed(made);
      setForm({ label: "", registration: "", driver_id: "" });
      setAdding(false);
      setSelectedId(made.id);
      reloadVehicles();
    }
  };

  const patch = async (v: Vehicle, body: Parameters<typeof api.patchVehicle>[1], message: string) => {
    if (await run(v.id, () => api.patchVehicle(v.id, body), message)) reloadVehicles();
  };

  const rotate = async (v: Vehicle) => {
    const next = await run(v.id, () => api.rotateVehicleKey(v.id), "New tracker key issued");
    if (next) {
      setRevealed(next);
      setConfirmKey(false);
      reloadVehicles();
    }
  };

  const endpoint = typeof window === "undefined" ? "" : `${window.location.origin}/api/v1/telemetry/gps`;

  return (
    <>
      <PageHead
        title="Live fleet"
        actions={
          <button className="btn btn-primary" onClick={() => setAdding((v) => !v)} aria-expanded={adding}>
            <Icon name="truck" />
            Add vehicle
          </button>
        }
      >
        Where every collection vehicle is right now, from a crew phone or a GPS tracker. Updates every few seconds.
      </PageHead>

      <div className="fleet-stats" role="list" aria-label="Fleet summary">
        <div className="fleet-stat" role="listitem" data-tone="moving">
          <b>{counts.moving}</b>
          <span>Moving</span>
        </div>
        <div className="fleet-stat" role="listitem" data-tone="idle">
          <b>{counts.idle}</b>
          <span>Stopped</span>
        </div>
        <div className="fleet-stat" role="listitem" data-tone="quiet">
          <b>{counts.quiet}</b>
          <span>Weak or offline</span>
        </div>
        <div className="fleet-stat" role="listitem">
          <b>{counts.none}</b>
          <span>Waiting for first signal</span>
        </div>
        <div className="fleet-stat" role="listitem">
          <b>{counts.km.toFixed(0)}</b>
          <span>km driven today</span>
        </div>
      </div>

      <ErrorNote message={actionError} />

      {revealed && (
        <section className="key-reveal" aria-live="polite">
          <header>
            <h2>Tracker key for {revealed.label}</h2>
            <button className="btn btn-sm" onClick={() => setRevealed(null)}>
              I have saved it
            </button>
          </header>
          <p className="muted">This key is shown only once. Anyone who has it can report positions for this vehicle, so keep it private. You can replace it at any time.</p>
          <div className="key-box">
            <code>{revealed.device_key}</code>
            <button
              className="btn btn-sm"
              onClick={() => {
                navigator.clipboard?.writeText(revealed.device_key).then(() => toast("Key copied"), () => toast("Copy failed. Select the key and copy it by hand."));
              }}
            >
              Copy
            </button>
          </div>
          <details>
            <summary>How a GPS tracker or a script reports</summary>
            <pre className="snippet">{`curl -X POST ${endpoint} \\
  -H "X-Device-Key: ${revealed.device_key}" \\
  -H "Content-Type: application/json" \\
  -d '{"lat": 30.7333, "lon": 76.7794, "speed_kmh": 24, "heading": 90}'`}</pre>
            <p className="muted">
              A tracker that was out of signal can send many fixes at once: <span className="mono">{`{"points": [{"lat": …, "lon": …, "recorded_at": "…"}, …]}`}</span>. Crews can also share their phone&apos;s location from their Work page.
            </p>
          </details>
        </section>
      )}

      {adding && (
        <form className="form form-wide" onSubmit={create}>
          <h2 className="h-sm">Add a vehicle</h2>
          <div className="split">
            <div className="field">
              <label htmlFor="v-label">Name</label>
              <input id="v-label" className="input" required maxLength={80} placeholder="Truck 7" value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="v-reg">Registration (optional)</label>
              <input id="v-reg" className="input mono" maxLength={40} placeholder="CH01 AB 1234" value={form.registration} onChange={(e) => setForm({ ...form, registration: e.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="v-driver">Driver (optional)</label>
              <select id="v-driver" className="select" value={form.driver_id} onChange={(e) => setForm({ ...form, driver_id: e.target.value })}>
                <option value="">No driver yet</option>
                {(workers.data ?? []).filter((w) => w.is_active).map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="row-actions">
            <button className="btn btn-primary" disabled={busy === "create" || !form.label.trim()}>
              {busy === "create" && <Spinner />}
              Add vehicle
            </button>
            <button type="button" className="btn" onClick={() => setAdding(false)}>
              Cancel
            </button>
          </div>
        </form>
      )}

      {vehicles.error && !vehicles.data ? (
        <Empty title="Could not load the fleet">{vehicles.error}</Empty>
      ) : !vehicles.data ? (
        <Loading />
      ) : list.length === 0 ? (
        <Empty
          title="No vehicles yet"
          action={
            <button className="btn btn-primary" onClick={() => setAdding(true)}>
              Add the first vehicle
            </button>
          }
        >
          Add a vehicle, then connect a GPS tracker or ask its driver to share their phone&apos;s location.
        </Empty>
      ) : (
        <div className="fleet">
          <FleetMap vehicles={list} sightings={sightings.data ?? []} trail={selected ? (trail.data ?? []) : []} selectedId={selectedId} onSelect={setSelectedId} focus={focus} />

          <aside className="fleet-side" aria-label="Vehicles">
            <ul className="fleet-list">
              {list.map((v) => (
                <li key={v.id}>
                  <button type="button" className="fleet-item" aria-pressed={v.id === selectedId} onClick={() => pick(v)}>
                    <span className="state-dot" data-state={v.state} aria-hidden="true" />
                    <span className="fleet-item-main">
                      <strong>{v.label}</strong>
                      <span className="muted">
                        {v.driver_name ?? "No driver"}
                        {v.registration ? ` · ${v.registration}` : ""}
                      </span>
                    </span>
                    <span className="fleet-item-meta">
                      <span className="state-chip" data-state={v.state}>
                        {STATE_LABEL[v.state]}
                      </span>
                      <span className="muted">{v.state === "moving" && v.speed_kmh !== null ? `${Math.round(v.speed_kmh)} km/h` : ago(v.age_seconds)}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>

            {selected && (
              <section className="fleet-detail" aria-label={`${selected.label} details`}>
                <h2>{selected.label}</h2>
                <dl className="facts">
                  <div>
                    <dt>Status</dt>
                    <dd>{STATE_LABEL[selected.state]}</dd>
                  </div>
                  <div>
                    <dt>Last seen</dt>
                    <dd>{ago(selected.age_seconds)}</dd>
                  </div>
                  <div>
                    <dt>Speed</dt>
                    <dd>{selected.speed_kmh !== null ? `${Math.round(selected.speed_kmh)} km/h` : "—"}</dd>
                  </div>
                  <div>
                    <dt>Driven today</dt>
                    <dd>{selected.distance_today_km.toFixed(1)} km</dd>
                  </div>
                  <div>
                    <dt>Source</dt>
                    <dd>{selected.source === "phone" ? "Crew phone" : selected.source === "device" ? "GPS tracker" : "—"}</dd>
                  </div>
                  <div>
                    <dt>Accuracy</dt>
                    <dd>{selected.accuracy_m !== null ? `about ${Math.round(selected.accuracy_m)} m` : "—"}</dd>
                  </div>
                </dl>
                <div className="field">
                  <label htmlFor="d-driver">Driver</label>
                  <select
                    id="d-driver"
                    className="select select-sm"
                    value={selected.driver_id ?? ""}
                    disabled={busy === selected.id}
                    onChange={(e) => patch(selected, { driver_id: e.target.value || null }, "Driver updated")}
                  >
                    <option value="">No driver</option>
                    {(workers.data ?? []).filter((w) => w.is_active).map((w) => (
                      <option key={w.id} value={w.id}>
                        {w.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="row-actions">
                  <button className="btn btn-sm" disabled={busy === selected.id} onClick={() => patch(selected, { is_active: !selected.is_active }, selected.is_active ? "Vehicle switched off" : "Vehicle switched on")}>
                    {selected.is_active ? "Switch off" : "Switch on"}
                  </button>
                  {confirmKey ? (
                    <>
                      <button className="btn btn-sm btn-danger" disabled={busy === selected.id} onClick={() => rotate(selected)}>
                        {busy === selected.id && <Spinner />}
                        Yes, replace the key
                      </button>
                      <button className="btn btn-sm" onClick={() => setConfirmKey(false)}>
                        Keep it
                      </button>
                    </>
                  ) : (
                    <button className="btn btn-sm" onClick={() => setConfirmKey(true)} title="The tracker using the old key stops reporting at once">
                      New tracker key
                    </button>
                  )}
                </div>
              </section>
            )}
          </aside>
        </div>
      )}
    </>
  );
}
