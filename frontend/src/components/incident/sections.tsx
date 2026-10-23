"use client";

import Link from "next/link";
import { useState } from "react";
import {
  api,
  STATUS_LABEL,
  type Analysis,
  type DuplicateCandidate,
  type DuplicateCluster,
  type Incident,
  type MediaAsset,
  type Risk,
  type SensorReading,
  type TimelineEvent,
  type Verification,
  type VerificationStatus,
  type WorkOrder,
} from "@/lib/api";
import { useAction, useLoad } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { AuthImage, ErrorNote, Icon, OrderBadge, RiskBar, Spinner, formatWhen, pct, shortId } from "../ui";

/* ------------------------------------------------------------------ photos */

export function PhotosSection({ incidentId, media, onChange }: { incidentId: string; media: MediaAsset[]; onChange: () => void }) {
  const { busy, error, run } = useAction();

  async function add(file: File | null) {
    if (!file) return;
    if (!file.type.startsWith("image/")) return;
    if (file.size > 10 * 1024 * 1024) return;
    const done = await run("upload", () => api.uploadMedia(incidentId, file), "Photo added");
    if (done) onChange();
  }

  return (
    <section className="section" aria-labelledby="photos">
      <h2 id="photos">Photos</h2>
      {media.length === 0 ? (
        <p className="muted">No photos yet. The AI needs at least one to assess severity.</p>
      ) : (
        <ul className="photo-grid">
          {media.map((asset, i) => (
            <li key={asset.id} className="photo" style={{ animationDelay: `${Math.min(i, 8) * 30}ms` }}>
              <AuthImage assetId={asset.id} alt={asset.is_after_cleanup ? "After cleanup" : "Before cleanup"} className="photo-img" />
              <span className="tag">{asset.is_after_cleanup ? "After cleanup" : "Before"}</span>
            </li>
          ))}
        </ul>
      )}
      <div>
        <label className="btn" style={{ cursor: busy ? "wait" : "pointer" }}>
          {busy ? <Spinner /> : <Icon name="image" />}
          {busy ? "Uploading" : "Add photo"}
          <input
            className="sr-only"
            type="file"
            accept="image/*"
            disabled={!!busy}
            onChange={(e) => {
              add(e.target.files?.[0] ?? null);
              e.target.value = "";
            }}
          />
        </label>
      </div>
      <ErrorNote message={error} />
    </section>
  );
}

/* ------------------------------------------------------------------ analysis */

export function AnalysisSection({
  incident,
  analysis,
  canRun,
  hasPhoto,
  onDone,
}: {
  incident: Incident;
  analysis: Analysis | null | undefined;
  canRun: boolean;
  hasPhoto: boolean;
  onDone: () => void;
}) {
  const { busy, error, run } = useAction();
  const [jobState, setJobState] = useState<string | null>(null);
  const pending = incident.status === "pending_analysis";

  async function runSync() {
    const done = await run("sync", () => api.analyze(incident.id), "Analysis complete");
    if (done) onDone();
  }

  async function runBackground() {
    await run("async", async () => {
      const queued = await api.analyzeAsync(incident.id);
      for (let i = 0; i < 60; i++) {
        const job = await api.getJob(queued.job_id);
        setJobState(job.status);
        if (job.status === "succeeded") return onDone();
        if (["failed", "dead_letter", "cancelled"].includes(job.status)) {
          throw new Error(job.last_error_message ?? "The analysis job failed");
        }
        await new Promise((resolve) => setTimeout(resolve, 1200));
      }
      throw new Error("The job is still waiting for a worker. Check back shortly.");
    });
    setJobState(null);
  }

  return (
    <section className="section" aria-labelledby="ai">
      <h2 id="ai">AI assessment</h2>
      {analysis ? (
        <div className="verdict">
          <dl>
            <dt>Category</dt>
            <dd>{analysis.category.replace(/_/g, " ")}</dd>
            <dt>Severity</dt>
            <dd>
              <span className="sev" data-level={analysis.severity ?? "none"}>
                {analysis.severity ?? "Not rated"}
              </span>
            </dd>
            <dt>Model</dt>
            <dd className="mono">{analysis.model_name}</dd>
          </dl>
          {analysis.confidence !== null && (
            <div>
              <div className="meter-head">
                <span className="muted">Confidence</span>
                <strong>{pct(analysis.confidence)}</strong>
              </div>
              <div className="meter" aria-hidden="true">
                <span style={{ "--v": analysis.confidence } as React.CSSProperties} />
              </div>
            </div>
          )}
          <span className="hint muted">The AI suggests. A supervisor decides.</span>
        </div>
      ) : pending ? (
        <p className="muted">
          {canRun
            ? hasPhoto
              ? "Photos attached. Run the analysis to categorise the site and rate its severity."
              : "Add a photo first, then run the analysis."
            : "Waiting for analysis by staff."}
        </p>
      ) : (
        <p className="muted">No AI analysis was recorded for this incident.</p>
      )}

      {jobState && <p className="muted">Background job: {jobState}…</p>}
      <ErrorNote message={error} />

      {canRun && pending && (
        <div className="btn-row">
          <button className="btn btn-primary" disabled={!!busy || !hasPhoto} onClick={runSync}>
            {busy === "sync" && <Spinner />}
            Run analysis
          </button>
          <button className="btn btn-quiet" disabled={!!busy || !hasPhoto} onClick={runBackground}>
            {busy === "async" && <Spinner />}
            Queue as background job
          </button>
        </div>
      )}
    </section>
  );
}

/* ------------------------------------------------------------------ risk */

const FACTOR_COPY: Record<string, [string, string]> = {
  recurrence: ["Recurrence", "Reports within 500 m in the last 90 days"],
  recency: ["Recency", "How recent those reports are"],
  severity: ["Severity", "What the AI rated this site"],
  unresolved: ["Still open", "Share of nearby reports not yet closed"],
};

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

export function RiskCard({
  incidentId,
  risk,
  canRecalc,
  onDone,
}: {
  incidentId: string;
  risk: Risk | null | undefined;
  canRecalc: boolean;
  onDone: () => void;
}) {
  const { busy, error, run } = useAction();
  const learned = risk?.kind === "probability";
  const movers = Object.entries(risk?.contributions ?? {})
    .filter(([, v]) => Math.abs(v) >= 0.005)
    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
    .slice(0, 4);

  return (
    <div className="panel-block">
      <h2>Hotspot risk</h2>
      {risk ? (
        <>
          <div className="risk-big">
            <RiskBar score={risk.score} probability={learned} />
            {risk.confidence !== null && <span className="muted">confidence {pct(risk.confidence)}</span>}
          </div>
          <p className="hint muted">
            {learned
              ? "Chance of another report within 500 m in the next 30 days."
              : "A 0 to 100 index from a hand-set formula. It is not a probability."}
          </p>
          <ul className="factors">
            {Object.entries(risk.factors).map(([key, value]) => (
              <li key={key}>
                <div className="meter-head">
                  <span title={FACTOR_COPY[key]?.[1]}>{FACTOR_COPY[key]?.[0] ?? key}</span>
                  <strong>{Math.round(value * 100)}</strong>
                </div>
                <div className="meter" aria-hidden="true">
                  <span style={{ "--v": value } as React.CSSProperties} />
                </div>
              </li>
            ))}
          </ul>
          {movers.length > 0 && (
            <div>
              <h3 className="h-xs">What moved this score</h3>
              <ul className="contrib">
                {movers.map(([key, value]) => (
                  <li key={key} data-sign={value > 0 ? "up" : "down"}>
                    <span>{FEATURE_LABEL[key] ?? key}</span>
                    <span className="contrib-val">
                      {value > 0 ? "+" : "−"}
                      {Math.abs(Math.round(value * 100))} pts
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <span className="hint muted">
            {learned ? `Trained model: ${risk.method.replace(/_/g, " ")}` : "Method: hand-set formula"} ·{" "}
            <span className="mono">{risk.model_version}</span>
          </span>
        </>
      ) : (
        <p className="muted">Not scored yet. The score is calculated automatically after AI analysis.</p>
      )}
      <ErrorNote message={error} />
      {canRecalc && (
        <div>
          <button
            className="btn"
            disabled={!!busy}
            onClick={async () => {
              if (await run("risk", () => api.calculateRisk(incidentId), "Risk recalculated")) onDone();
            }}
          >
            {busy && <Spinner />}
            {risk ? "Recalculate" : "Calculate now"}
          </button>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ supervisor decision */

export function DecisionCard({ incident, onDone }: { incident: Incident; onDone: () => void }) {
  const { busy, error, run } = useAction();
  const open = incident.status === "ready_for_review" || incident.status === "uncertain";
  if (!open) return null;
  const go = async (status: "rejected" | "uncertain" | "ready_for_review", message: string) => {
    if (await run(status, () => api.changeStatus(incident.id, status), message)) onDone();
  };
  return (
    <div className="panel-block">
      <h2>Review decision</h2>
      <p className="muted">Open a work order below to approve this cleanup, or close the report out.</p>
      <div className="btn-row">
        {incident.status === "ready_for_review" ? (
          <button className="btn" disabled={!!busy} onClick={() => go("uncertain", "Marked uncertain")}>
            {busy === "uncertain" && <Spinner />}
            Mark uncertain
          </button>
        ) : (
          <button className="btn" disabled={!!busy} onClick={() => go("ready_for_review", "Back in review")}>
            {busy === "ready_for_review" && <Spinner />}
            Back to review
          </button>
        )}
        <button className="btn btn-danger" disabled={!!busy} onClick={() => go("rejected", "Report rejected")}>
          {busy === "rejected" && <Spinner />}
          Reject report
        </button>
      </div>
      <ErrorNote message={error} />
    </div>
  );
}

/* ------------------------------------------------------------------ work order (supervisor) */

export function WorkOrderCard({
  incident,
  orders,
  risk,
  onDone,
}: {
  incident: Incident;
  orders: WorkOrder[];
  risk: Risk | null | undefined;
  onDone: () => void;
}) {
  const { busy, error, run } = useAction();
  const active = orders.find((o) => o.status !== "cancelled");
  const workers = useLoad(() => (active?.status === "approved" ? api.listUsers("sanitation_worker") : Promise.resolve([])), [active?.status]);
  const [priority, setPriority] = useState<string>("");
  const [volume, setVolume] = useState("");
  const [workerId, setWorkerId] = useState("");
  const [overridePriority, setOverridePriority] = useState("");
  const [reason, setReason] = useState("");

  const suggested = risk ? Math.max(1, Math.round(risk.score * 10)) : 5;
  const after = async (promise: Promise<unknown>, key: string, message: string) => {
    if (await run(key, () => promise, message)) onDone();
  };

  return (
    <div className="panel-block">
      <h2>Work order</h2>
      {!active ? (
        incident.status === "ready_for_review" ? (
          <form
            className="form"
            onSubmit={(e) => {
              e.preventDefault();
              after(
                api.createOrder(incident.id, {
                  priority: Number(priority || suggested),
                  estimated_volume: volume === "" ? null : Number(volume),
                }),
                "create",
                "Work order created",
              );
            }}
          >
            <div className="split">
              <div className="field">
                <label htmlFor="wo-priority">Priority (0-100)</label>
                <input id="wo-priority" className="input" type="number" min={0} max={100} value={priority} placeholder={String(suggested)} onChange={(e) => setPriority(e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="wo-volume">Volume (m³)</label>
                <input id="wo-volume" className="input" type="number" min={0} step="0.1" value={volume} placeholder="optional" onChange={(e) => setVolume(e.target.value)} />
              </div>
            </div>
            <span className="hint muted">Priority is pre-filled from the risk score.</span>
            <button className="btn btn-primary" disabled={!!busy}>
              {busy === "create" && <Spinner />}
              Create work order
            </button>
          </form>
        ) : (
          <p className="muted">A work order can be opened once the incident is ready for review.</p>
        )
      ) : (
        <>
          <dl className="kv">
            <dt>Status</dt>
            <dd>
              <OrderBadge status={active.status} />
            </dd>
            <dt>Priority</dt>
            <dd>{active.priority}</dd>
            <dt>Volume</dt>
            <dd>{active.estimated_volume ?? "–"}</dd>
            <dt>Assigned</dt>
            <dd>{active.assigned_to_name ?? "Nobody yet"}</dd>
          </dl>
          {active.override_reason && <p className="hint muted">Override: {active.override_reason}</p>}

          {active.status === "draft" && (
            <button className="btn btn-primary" disabled={!!busy} onClick={() => after(api.approveOrder(active.id), "approve", "Approved for cleanup")}>
              {busy === "approve" && <Spinner />}
              Approve for cleanup
            </button>
          )}

          {active.status === "approved" && (
            <div className="form">
              <div className="field">
                <label htmlFor="assign">Assign to</label>
                <select id="assign" className="select" value={workerId} onChange={(e) => setWorkerId(e.target.value)}>
                  <option value="">Choose a worker</option>
                  {(workers.data ?? []).filter((w) => w.is_active).map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name}
                    </option>
                  ))}
                </select>
              </div>
              <button className="btn btn-primary" disabled={!!busy || !workerId} onClick={() => after(api.assignOrder(active.id, workerId), "assign", "Worker assigned")}>
                {busy === "assign" && <Spinner />}
                Assign worker
              </button>
              <span className="hint muted">
                Batching stops? <Link href="/routes">Plan a route</Link> first.
              </span>
            </div>
          )}

          {(active.status === "draft" || active.status === "approved" || active.status === "assigned" || active.status === "in_progress") && (
            <form
              className="form"
              onSubmit={(e) => {
                e.preventDefault();
                after(api.overridePriority(incident.id, Number(overridePriority), reason.trim()), "override", "Priority changed");
                setReason("");
              }}
            >
              <div className="field">
                <label htmlFor="ov-priority">Override priority</label>
                <input id="ov-priority" className="input" type="number" min={0} max={100} required value={overridePriority} onChange={(e) => setOverridePriority(e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="ov-reason">Reason</label>
                <input id="ov-reason" className="input" required value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why does this jump the queue?" />
              </div>
              <button className="btn" disabled={!!busy}>
                {busy === "override" && <Spinner />}
                Apply override
              </button>
            </form>
          )}
        </>
      )}
      <ErrorNote message={error} />
    </div>
  );
}

/* ------------------------------------------------------------------ worker */

export function WorkerCard({ incident, orders, onDone }: { incident: Incident; orders: WorkOrder[]; onDone: () => void }) {
  const { principal } = useAuth();
  const { busy, error, run } = useAction();
  const [notes, setNotes] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const mine = orders.find((o) => o.assigned_to === principal?.userId && o.status !== "cancelled");

  const after = async (promise: Promise<unknown>, key: string, message: string) => {
    if (await run(key, () => promise, message)) onDone();
  };

  return (
    <div className="panel-block">
      <h2>Your assignment</h2>
      {!mine ? (
        <p className="muted">This incident is not assigned to you.</p>
      ) : (
        <>
          <dl className="kv">
            <dt>Order</dt>
            <dd>
              <OrderBadge status={mine.status} />
            </dd>
            <dt>Priority</dt>
            <dd>{mine.priority}</dd>
          </dl>
          {mine.status === "assigned" && (
            <button className="btn btn-primary" disabled={!!busy} onClick={() => after(api.startOrder(mine.id), "start", "Work started")}>
              {busy === "start" && <Spinner />}
              Start work
            </button>
          )}
          {(mine.status === "assigned" || mine.status === "in_progress") && (
            <button className="btn" disabled={!!busy} onClick={() => after(api.completeOrder(mine.id), "complete", "Marked complete")}>
              {busy === "complete" && <Spinner />}
              Mark cleanup complete
            </button>
          )}
          {mine.status === "completed" && incident.status !== "verified" && (
            <form
              className="form"
              onSubmit={(e) => {
                e.preventDefault();
                if (file) after(api.submitVerification(incident.id, file, notes.trim()), "verify", "Evidence submitted");
              }}
            >
              <div className="field">
                <label htmlFor="after-photo">After-cleanup photo</label>
                <input id="after-photo" className="input" type="file" accept="image/*" required onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
              </div>
              <div className="field">
                <label htmlFor="after-notes">Notes</label>
                <input id="after-notes" className="input" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="optional" />
              </div>
              <button className="btn btn-primary" disabled={!!busy || !file}>
                {busy === "verify" && <Spinner />}
                Submit evidence
              </button>
              <span className="hint muted">Clear cases verify automatically. Anything doubtful goes to a supervisor.</span>
            </form>
          )}
        </>
      )}
      <ErrorNote message={error} />
    </div>
  );
}

/* ------------------------------------------------------------------ verification */

const VERIFICATION_TONE: Record<VerificationStatus, string> = {
  pending: "pending_analysis",
  verified: "verified",
  uncertain: "uncertain",
  rejected: "rejected",
};

export function VerificationSection({
  verification,
  canReview,
  onDone,
}: {
  verification: Verification | null | undefined;
  canReview: boolean;
  onDone: () => void;
}) {
  const { busy, error, run } = useAction();
  const [reason, setReason] = useState("");
  if (!verification) return null;

  const review = async (status: VerificationStatus) => {
    if (await run(status, () => api.reviewVerification(verification.id, status, reason.trim()), "Review saved")) {
      setReason("");
      onDone();
    }
  };

  return (
    <section className="section" aria-labelledby="verification">
      <h2 id="verification">Cleanup verification</h2>
      <div className="detail-meta" style={{ margin: 0 }}>
        <span className="badge" data-status={VERIFICATION_TONE[verification.status]}>
          {verification.status === "verified" ? "Verified" : verification.status === "uncertain" ? "Needs supervisor review" : verification.status === "rejected" ? "Rejected" : "Pending"}
        </span>
        <span className="muted">Submitted {formatWhen(verification.created_at)}</span>
      </div>
      {verification.evidence_notes && <p>Worker note: {verification.evidence_notes}</p>}
      {verification.review_reason && <p className="muted">Reviewed: {verification.review_reason}</p>}
      {canReview && (
        <div className="form">
          <div className="field">
            <label htmlFor="review-reason">Review reason</label>
            <input id="review-reason" className="input" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="What did you check in the photos?" />
          </div>
          <div className="btn-row">
            <button className="btn btn-primary" disabled={!!busy || !reason.trim()} onClick={() => review("verified")}>
              {busy === "verified" && <Spinner />}
              Confirm cleaned
            </button>
            <button className="btn" disabled={!!busy || !reason.trim()} onClick={() => review("uncertain")}>
              Still unsure
            </button>
            <button className="btn btn-danger" disabled={!!busy || !reason.trim()} onClick={() => review("rejected")}>
              Send back to field
            </button>
          </div>
        </div>
      )}
      <ErrorNote message={error} />
    </section>
  );
}

/* ------------------------------------------------------------------ duplicates */

export function DuplicatesSection({ incidentId }: { incidentId: string }) {
  const { data, error, loading, reload } = useLoad(() => api.duplicates(incidentId), [incidentId]);
  const { busy, error: actionError, run } = useAction();
  const [picked, setPicked] = useState<Set<string>>(new Set());

  const toggle = (id: string) =>
    setPicked((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const act = async (key: string, fn: () => Promise<unknown>, message: string) => {
    if (await run(key, fn, message)) {
      setPicked(new Set());
      reload();
    }
  };

  const candidates: DuplicateCandidate[] = data?.candidates ?? [];
  const clusters: DuplicateCluster[] = data?.clusters ?? [];

  return (
    <section className="section" aria-labelledby="dupes">
      <h2 id="dupes">Possible duplicates</h2>
      {loading && !data ? (
        <p className="muted">Checking nearby reports…</p>
      ) : error ? (
        <ErrorNote message={error} />
      ) : (
        <>
          {candidates.length === 0 ? (
            <p className="muted">No other report within 250 m and 24 hours looks like this one.</p>
          ) : (
            <ul className="assets">
              {candidates.map((c) => (
                <li key={c.incident.id} className="asset">
                  <label className="check">
                    <input type="checkbox" checked={picked.has(c.incident.id)} disabled={c.already_grouped} onChange={() => toggle(c.incident.id)} />
                    <span>
                      <Link href={`/incidents/${c.incident.id}`}>{c.incident.description}</Link>
                      <span className="muted"> · {STATUS_LABEL[c.incident.status]}</span>
                    </span>
                  </label>
                  <div className="why">
                    <span className="tag">
                      {pct(c.similarity_score)} match{c.already_grouped ? " · grouped" : ""}
                    </span>
                    <span className="why-chips" title={c.text_method === "embedding" ? "Description compared by meaning" : "Description compared by shared words"}>
                      <span>near {pct(c.factors.distance)}</span>
                      <span>time {pct(c.factors.time)}</span>
                      <span>{c.text_method === "embedding" ? "meaning" : "words"} {pct(c.factors.text)}</span>
                      <span>{c.factors.category ? "same category" : "category differs"}</span>
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {candidates.length > 0 && (
            <div>
              <button className="btn" disabled={!!busy || picked.size === 0} onClick={() => act("group", () => api.createCluster(incidentId, [...picked]), "Grouped for review")}>
                {busy === "group" && <Spinner />}
                Group selected as duplicates
              </button>
            </div>
          )}
          {clusters.map((cluster) => (
            <div key={cluster.id} className="cluster">
              <div className="meter-head">
                <strong>{cluster.confirmed ? "Confirmed duplicate group" : "Suggested group"}</strong>
                <span className="muted">{cluster.members.length} reports</span>
              </div>
              <ul className="plain">
                {cluster.members.map((m) => (
                  <li key={m.incident_id}>
                    <Link href={`/incidents/${m.incident_id}`}>{m.description}</Link>
                  </li>
                ))}
              </ul>
              <div className="btn-row">
                {!cluster.confirmed && (
                  <button className="btn btn-primary" disabled={!!busy} onClick={() => act("confirm" + cluster.id, () => api.confirmCluster(cluster.id), "Duplicates confirmed")}>
                    Confirm duplicates
                  </button>
                )}
                <button className="btn" disabled={!!busy} onClick={() => act("reject" + cluster.id, () => api.rejectCluster(cluster.id), "Marked not duplicates")}>
                  {cluster.confirmed ? "Undo" : "Not duplicates"}
                </button>
              </div>
            </div>
          ))}
        </>
      )}
      <ErrorNote message={actionError} />
    </section>
  );
}

/* ------------------------------------------------------------------ sensors */

export function SensorsSection({ incidentId }: { incidentId: string }) {
  const { data, loading, error, reload } = useLoad(() => api.incidentSensors(incidentId), [incidentId]);
  const { busy, error: actionError, run } = useAction();
  const readings: SensorReading[] = data ?? [];

  return (
    <section className="section" aria-labelledby="sensors">
      <h2 id="sensors">Nearby sensors</h2>
      {loading && !data ? (
        <p className="muted">Looking for sensors…</p>
      ) : error ? (
        <ErrorNote message={error} />
      ) : readings.length === 0 ? (
        <p className="muted">No sensor readings near this site.</p>
      ) : (
        <ul className="assets">
          {readings.map((r) => (
            <li key={r.id} className="asset">
              <span>
                <strong>{r.sensor_id}</strong> <span className="mono muted">{Object.entries(r.reading).map(([k, v]) => `${k}: ${String(v)}`).join(" · ")}</span>
                <span className="muted"> · {formatWhen(r.observed_at)}</span>
              </span>
              {r.incident_id === incidentId ? (
                <span className="tag">Linked</span>
              ) : (
                <button
                  className="btn"
                  disabled={!!busy}
                  onClick={async () => {
                    if (await run(r.id, () => api.associateReading(r.id, incidentId), "Sensor linked")) reload();
                  }}
                >
                  {busy === r.id && <Spinner />}
                  Link to this incident
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      <ErrorNote message={actionError} />
    </section>
  );
}

/* ------------------------------------------------------------------ timeline */

export function TimelineSection({ events }: { events: TimelineEvent[] | undefined }) {
  if (!events || events.length === 0) return null;
  return (
    <section className="section" aria-labelledby="history">
      <h2 id="history">History</h2>
      <ol className="timeline">
        {events.map((e) => (
          <li key={e.id}>
            <span className="timeline-action">{e.action.replace(/_/g, " ")}</span>
            <span className="muted">
              {e.actor_name} · {formatWhen(e.created_at)}
              {e.details?.reason ? ` · ${String(e.details.reason)}` : ""}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}

export { shortId };
