"use client";

import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Empty, ErrorNote, Loading, PageHead, Spinner, formatWhen } from "@/components/ui";
import { SUPERVISORS } from "@/lib/access";
import { api, type ModelMetrics, type Run } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useAction, useLoad } from "@/lib/hooks";

export default function InsightsPage() {
  return (
    <AppShell roles={SUPERVISORS}>
      <Insights />
    </AppShell>
  );
}

const METRIC_LABEL: Record<string, string> = {
  incidents_total: "Reports received",
  verified_closure_rate: "Verified closure rate",
  mean_ai_confidence: "Mean AI confidence",
  mean_route_saving: "Mean route saving",
  supervisor_override_rate: "Supervisor override rate",
};
const RATES = new Set(["verified_closure_rate", "mean_ai_confidence", "mean_route_saving", "supervisor_override_rate"]);

function formatMetric(key: string, value: number | string) {
  if (typeof value === "number" && RATES.has(key)) return `${Math.round(value * 1000) / 10}%`;
  return String(value);
}

function Insights() {
  const [tab, setTab] = useState<"evaluations" | "pilots" | "models">("evaluations");
  return (
    <>
      <PageHead title="Insights">Measure how the workflow performs, and run the 8 to 12 week pilot against a baseline.</PageHead>
      <div className="tabs" role="tablist" aria-label="Insights">
        {(["evaluations", "pilots", "models"] as const).map((t) => (
          <button key={t} type="button" role="tab" aria-selected={tab === t} className="tab" onClick={() => setTab(t)}>
            {t === "evaluations" ? "Evaluations" : t === "pilots" ? "Pilots" : "Models"}
          </button>
        ))}
      </div>
      {tab === "evaluations" ? <Evaluations /> : tab === "pilots" ? <Pilots /> : <Models />}
    </>
  );
}

function Evaluations() {
  const { data, error, loading, reload } = useLoad(() => api.listEvaluations(), []);
  const { busy, error: actionError, run } = useAction();
  const [name, setName] = useState("System snapshot");
  const [open, setOpen] = useState<string | null>(null);
  const comparison = useLoad(() => (open ? api.evaluationComparison(open) : Promise.resolve(null)), [open]);

  return (
    <>
      <form
        className="inline-form"
        onSubmit={async (e) => {
          e.preventDefault();
          if (await run("run", () => api.runEvaluation({ name: name.trim(), dataset_version: "live" }), "Evaluation recorded")) reload();
        }}
      >
        <div className="field grow">
          <label htmlFor="eval-name">Snapshot name</label>
          <input id="eval-name" className="input" required value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <button className="btn btn-primary" disabled={!!busy}>
          {busy && <Spinner />}
          Run evaluation on live data
        </button>
      </form>
      <ErrorNote message={actionError} />

      {error ? (
        <ErrorNote message={error} />
      ) : loading && !data ? (
        <Loading />
      ) : (data ?? []).length === 0 ? (
        <Empty title="No evaluations yet">A snapshot records closure rate, AI confidence and route savings from the live data.</Empty>
      ) : (
        <div className="cards">
          {(data ?? []).map((run) => (
            <article key={run.id} className="card">
              <header>
                <h3>{run.name}</h3>
                <span className="muted">{formatWhen(run.created_at)}</span>
              </header>
              <dl className="kv">
                {Object.entries(run.metrics).map(([k, v]) => (
                  <div key={k} className="kv-row">
                    <dt>{METRIC_LABEL[k] ?? k.replace(/_/g, " ")}</dt>
                    <dd>{formatMetric(k, v)}</dd>
                  </div>
                ))}
              </dl>
              <button className="btn btn-quiet" onClick={() => setOpen(open === run.id ? null : run.id)} aria-expanded={open === run.id}>
                {open === run.id ? "Hide baseline comparison" : "Compare with baseline"}
              </button>
              {open === run.id && (
                <div className="compare">
                  {comparison.loading && !comparison.data ? (
                    <span className="muted">Loading…</span>
                  ) : (
                    <table className="tbl">
                      <thead>
                        <tr>
                          <th>Metric</th>
                          <th>Value</th>
                          <th>Baseline</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(comparison.data ?? {}).map(([k, v]) => (
                          <tr key={k}>
                            <td>{METRIC_LABEL[k] ?? k}</td>
                            <td>{formatMetric(k, v.value)}</td>
                            <td>{v.baseline === null || v.baseline === undefined ? "none set" : formatMetric(k, v.baseline)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </>
  );
}

function Pilots() {
  const { data, error, loading, reload } = useLoad(() => api.listPilots(), []);
  const { busy, error: actionError, run } = useAction();
  const [form, setForm] = useState({ name: "", location: "", start_date: "", end_date: "", baseline_version: "" });
  const [metric, setMetric] = useState<Record<string, { key: string; value: string }>>({});
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  const addMetric = async (pilot: Run) => {
    const m = metric[pilot.id];
    if (!m?.key.trim() || m.value === "") return;
    const value = Number.isFinite(Number(m.value)) ? Number(m.value) : m.value;
    if (await run(pilot.id, () => api.pilotMetrics(pilot.id, { [m.key.trim()]: value }), "Metric recorded")) {
      setMetric({ ...metric, [pilot.id]: { key: "", value: "" } });
      reload();
    }
  };

  return (
    <>
      <form
        className="form form-wide"
        onSubmit={async (e) => {
          e.preventDefault();
          if (await run("start", () => api.startPilot(form), "Pilot started")) {
            setForm({ name: "", location: "", start_date: "", end_date: "", baseline_version: "" });
            reload();
          }
        }}
      >
        <h2 className="h-sm">Start a pilot</h2>
        <div className="split">
          <div className="field">
            <label htmlFor="p-name">Name</label>
            <input id="p-name" className="input" required value={form.name} onChange={set("name")} />
          </div>
          <div className="field">
            <label htmlFor="p-loc">Location</label>
            <input id="p-loc" className="input" required value={form.location} onChange={set("location")} placeholder="Sector 17, Chandigarh" />
          </div>
          <div className="field">
            <label htmlFor="p-start">Starts</label>
            <input id="p-start" className="input" type="date" required value={form.start_date} onChange={set("start_date")} />
          </div>
          <div className="field">
            <label htmlFor="p-end">Ends</label>
            <input id="p-end" className="input" type="date" required value={form.end_date} onChange={set("end_date")} />
          </div>
        </div>
        <div className="field">
          <label htmlFor="p-base">Baseline version</label>
          <input id="p-base" className="input" required value={form.baseline_version} onChange={set("baseline_version")} placeholder="q3-2026-manual-process" />
          <span className="hint">Name the period or dataset you will compare against. A pilot must run 8 to 12 weeks.</span>
        </div>
        <div>
          <button className="btn btn-primary" disabled={!!busy}>
            {busy === "start" && <Spinner />}
            Start pilot
          </button>
        </div>
      </form>
      <ErrorNote message={actionError} />

      {error ? (
        <ErrorNote message={error} />
      ) : loading && !data ? (
        <Loading />
      ) : (data ?? []).length === 0 ? (
        <Empty title="No pilots yet">Pilots you start will be tracked here.</Empty>
      ) : (
        <div className="cards">
          {(data ?? []).map((pilot) => {
            const { location, start_date, end_date, ...rest } = pilot.metrics;
            const m = metric[pilot.id] ?? { key: "", value: "" };
            return (
              <article key={pilot.id} className="card">
                <header>
                  <h3>{pilot.name}</h3>
                  <span className="muted">
                    {String(location)} · {String(start_date)} to {String(end_date)}
                  </span>
                </header>
                <p className="muted">Baseline: {pilot.dataset_version}</p>
                {Object.keys(rest).length > 0 && (
                  <dl className="kv">
                    {Object.entries(rest).map(([k, v]) => (
                      <div key={k} className="kv-row">
                        <dt>{k.replace(/_/g, " ")}</dt>
                        <dd>{String(v)}</dd>
                      </div>
                    ))}
                  </dl>
                )}
                <div className="inline-form">
                  <div className="field grow">
                    <label htmlFor={`mk-${pilot.id}`}>Metric</label>
                    <input id={`mk-${pilot.id}`} className="input" value={m.key} placeholder="resolution_hours" onChange={(e) => setMetric({ ...metric, [pilot.id]: { ...m, key: e.target.value } })} />
                  </div>
                  <div className="field">
                    <label htmlFor={`mv-${pilot.id}`}>Value</label>
                    <input id={`mv-${pilot.id}`} className="input" value={m.value} onChange={(e) => setMetric({ ...metric, [pilot.id]: { ...m, value: e.target.value } })} />
                  </div>
                  <button className="btn" disabled={!!busy || !m.key.trim() || m.value === ""} onClick={() => addMetric(pilot)}>
                    Record
                  </button>
                  <button
                    className="btn btn-danger"
                    disabled={!!busy}
                    onClick={async () => {
                      if (await run("close" + pilot.id, () => api.closePilot(pilot.id), "Pilot closure logged")) reload();
                    }}
                  >
                    Close pilot
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </>
  );
}

const FEATURE_LABEL: Record<string, string> = {
  reports_7d: "Reports nearby this week",
  reports_30d: "Reports nearby this month",
  reports_90d: "Reports nearby in 90 days",
  decayed_recency: "Freshness of nearby reports",
  days_since_last: "Days since last nearby report",
  severity: "AI severity rating",
  has_ai_rating: "Has an AI rating",
  ai_confidence: "AI confidence",
};

const METRIC_ROWS: { key: keyof ModelMetrics; label: string; higherIsBetter: boolean; hint: string }[] = [
  { key: "auc", label: "AUC", higherIsBetter: true, hint: "Chance a recurring site scores above a non-recurring one. 0.5 is a coin flip." },
  { key: "average_precision", label: "Average precision", higherIsBetter: true, hint: "How clean the top of the ranking is." },
  { key: "precision_at_10pct", label: "Precision in the top 10%", higherIsBetter: true, hint: "Of the 10% scored riskiest, how many really recurred." },
  { key: "brier", label: "Brier score", higherIsBetter: false, hint: "Error of the probabilities. Lower is better." },
];

function Models() {
  const { principal } = useAuth();
  const { data, error, loading, reload } = useLoad(() => api.mlStatus(), []);
  const { busy, error: actionError, run } = useAction();

  if (error) return <ErrorNote message={error} />;
  if (loading && !data) return <Loading />;
  if (!data) return null;

  const meta = data.risk.last_run;
  const learned = data.risk.active === "model";
  const win = (key: keyof ModelMetrics, higher: boolean) =>
    meta?.metrics && meta.baseline ? (higher ? meta.metrics[key] > meta.baseline[key] : meta.metrics[key] < meta.baseline[key]) : false;
  const importance = Object.entries(meta?.importance ?? {})
    .filter(([, v]) => v > 0.002)
    .sort((a, b) => b[1] - a[1]);
  const top = importance[0]?.[1] ?? 1;

  return (
    <div className="cards" style={{ gridTemplateColumns: "minmax(0, 1fr)" }}>
      <article className="card">
        <header>
          <h3>Risk scoring</h3>
          <span className="muted">
            Active: {learned ? `trained ${data.risk.current?.algorithm?.replace(/_/g, " ")} (${data.risk.current?.version})` : "hand-set formula"}
          </span>
        </header>
        <p className="muted">
          The trained model predicts the chance that another report appears within 500 m in the next 30 days. It replaces the hand-set formula only if it beats it on reports it has never seen.
        </p>
        {meta && meta.synthetic_share > 0 && (
          <p className="notice" role="note">
            {Math.round(meta.synthetic_share * 100)}% of the training data is simulated. This shows the training pipeline works; it does not show real-world accuracy. Retrain once real reports have built up.
          </p>
        )}
        {meta ? (
          <>
            <p>{meta.reason}</p>
            <dl className="kv">
              <div className="kv-row">
                <dt>Reports with a known outcome</dt>
                <dd>{meta.rows_labelled}</dd>
              </div>
              <div className="kv-row">
                <dt>Went on to recur</dt>
                <dd>{meta.positive_rate !== null ? `${Math.round(meta.positive_rate * 100)}%` : "–"}</dd>
              </div>
              {meta.validation_rows ? (
                <div className="kv-row">
                  <dt>Tested on</dt>
                  <dd>newest {meta.validation_rows} reports</dd>
                </div>
              ) : null}
              <div className="kv-row">
                <dt>Last trained</dt>
                <dd>{formatWhen(meta.trained_at)}</dd>
              </div>
            </dl>
            {meta.metrics && meta.baseline && (
              <div className="compare">
                <table className="tbl compare-table">
                  <thead>
                    <tr>
                      <th>On unseen reports</th>
                      <th>Trained model</th>
                      <th>Hand-set formula</th>
                    </tr>
                  </thead>
                  <tbody>
                    {METRIC_ROWS.map((m) => (
                      <tr key={m.key} title={m.hint}>
                        <td>{m.label}</td>
                        <td className={win(m.key, m.higherIsBetter) ? "win" : undefined}>{meta.metrics![m.key].toFixed(3)}</td>
                        <td>{meta.baseline![m.key].toFixed(3)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {meta.candidates && (
              <p className="hint muted">
                Compared: {Object.entries(meta.candidates).map(([k, v]) => `${k.replace(/_/g, " ")} (AUC ${v.auc.toFixed(3)})`).join(" and ")}. Tested chronologically: trained on the oldest 70%, scored on the newest 30%.
              </p>
            )}
            {importance.length > 0 && (
              <div>
                <h3 className="h-xs">What the model relies on</h3>
                <ul className="factors">
                  {importance.map(([k, v]) => (
                    <li key={k}>
                      <div className="meter-head">
                        <span>{FEATURE_LABEL[k] ?? k}</span>
                      </div>
                      <div className="meter" aria-hidden="true">
                        <span style={{ "--v": v / top } as React.CSSProperties} />
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        ) : (
          <p className="muted">The model has not been trained yet. The hand-set formula is scoring reports.</p>
        )}
        <ErrorNote message={actionError} />
        {principal?.role === "admin" ? (
          <div>
            <button
              className="btn btn-primary"
              disabled={!!busy}
              onClick={async () => {
                if (await run("train", () => api.trainRisk(), "Training finished")) reload();
              }}
            >
              {busy && <Spinner />}
              Train risk model now
            </button>
          </div>
        ) : (
          <p className="hint muted">Only an admin can retrain the model.</p>
        )}
      </article>

      <article className="card">
        <header>
          <h3>Duplicate detection</h3>
          <span className="muted">{data.duplicates.loaded ? "Comparing descriptions by meaning" : "Comparing descriptions by shared words"}</span>
        </header>
        <p className="muted">
          Reports within 250 m and 24 hours are scored on distance, time, description and AI category. Descriptions are compared with sentence embeddings
          {data.duplicates.name ? ` (${data.duplicates.name.replace("fastembed:", "")})` : ""} when available, so &ldquo;overflowing bins&rdquo; matches &ldquo;garbage piled up&rdquo;.
        </p>
        {!data.duplicates.loaded && (
          <p className="notice" role="note">
            {data.duplicates.enabled
              ? `The embedding model is still loading or could not load${data.duplicates.error ? ` (${data.duplicates.error})` : ""}. Word overlap is used meanwhile.`
              : "Embeddings are switched off on this server. Word overlap is used."}
          </p>
        )}
      </article>

      <article className="card">
        <header>
          <h3>Route planning</h3>
          <span className="muted">{data.routing.solver === "ortools" ? "Google OR-Tools" : "Nearest-neighbour"}</span>
        </header>
        <p className="muted">
          {data.routing.solver === "ortools"
            ? "Routes are optimised with guided local search, starting from the nearest-neighbour route so a plan is never worse than it. Urgent stops are pulled earlier, and an optional drive-time limit is enforced."
            : "OR-Tools is not installed, so routes use nearest-neighbour ordering."}
        </p>
      </article>
    </div>
  );
}
