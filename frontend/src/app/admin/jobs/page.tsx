"use client";

import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Empty, ErrorNote, Loading, PageHead, formatWhen, shortId } from "@/components/ui";
import { api, type Job } from "@/lib/api";
import { useAction, useLoad } from "@/lib/hooks";

export default function JobsPage() {
  return (
    <AppShell roles={["admin"]}>
      <Jobs />
    </AppShell>
  );
}

const STATUSES: (Job["status"] | "all")[] = ["all", "queued", "running", "succeeded", "failed", "dead_letter", "cancelled"];
const TONE: Record<Job["status"], string> = {
  queued: "ready_for_review",
  running: "in_progress",
  succeeded: "verified",
  failed: "rejected",
  dead_letter: "rejected",
  cancelled: "pending_analysis",
};

function Jobs() {
  const [filter, setFilter] = useState<Job["status"] | "all">("all");
  const { data, error, loading, reload } = useLoad(() => api.listJobs(filter === "all" ? undefined : filter), [filter]);
  const system = useLoad(() => api.systemStatus(), []);
  const { busy, error: actionError, run } = useAction();

  return (
    <>
      <PageHead
        title="Background jobs"
        actions={
          <button className="btn" onClick={reload}>
            Refresh
          </button>
        }
      >
        AI analysis and other long tasks run here. Retry anything that failed.
      </PageHead>

      {system.data && (
        <dl className="facts stat-row">
          <div>
            <dt>AI analysis</dt>
            <dd>{system.data.ai_configured ? `On (${system.data.ai_provider})` : "Not configured"}</dd>
          </div>
          <div>
            <dt>Worker</dt>
            <dd>{system.data.worker}</dd>
          </div>
          <div>
            <dt>Queue</dt>
            <dd>{system.data.queue.replace("JobQueue", "")}</dd>
          </div>
          <div>
            <dt>Photo storage</dt>
            <dd>{system.data.storage.replace("ObjectStorage", "")}</dd>
          </div>
          <div>
            <dt>Waiting</dt>
            <dd>{system.data.jobs_queued}</dd>
          </div>
        </dl>
      )}

      <div className="tabs" role="tablist" aria-label="Job status" style={{ marginTop: 24 }}>
        {STATUSES.map((s) => (
          <button key={s} type="button" role="tab" aria-selected={filter === s} className="tab" onClick={() => setFilter(s)}>
            {s === "all" ? "All" : s.replace("_", " ")}
          </button>
        ))}
      </div>

      <ErrorNote message={actionError} />
      <div className="table-wrap">
        {error ? (
          <Empty title="Could not load jobs">{error}</Empty>
        ) : loading && !data ? (
          <Loading />
        ) : (data ?? []).length === 0 ? (
          <Empty title="No jobs">Jobs appear when someone queues an analysis in the background.</Empty>
        ) : (
          <table className="tbl">
            <thead>
              <tr>
                <th>Job</th>
                <th>Status</th>
                <th>Attempts</th>
                <th>Created</th>
                <th>Detail</th>
                <th>
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {(data ?? []).map((job) => (
                <tr key={job.id}>
                  <td>
                    {job.job_type.replace(/_/g, " ")}
                    <div className="muted mono">{shortId(job.id)}</div>
                  </td>
                  <td>
                    <span className="badge" data-status={TONE[job.status]}>
                      {job.status.replace("_", " ")}
                    </span>
                  </td>
                  <td>
                    {job.attempt_count}/{job.max_attempts}
                  </td>
                  <td>{formatWhen(job.created_at)}</td>
                  <td className="cell-wrap">{job.last_error_message ?? (job.result ? JSON.stringify(job.result) : "")}</td>
                  <td>
                    <div className="btn-row">
                      {(job.status === "failed" || job.status === "dead_letter") && (
                        <button className="btn" disabled={!!busy} onClick={async () => (await run(job.id, () => api.retryJob(job.id), "Job re-queued")) && reload()}>
                          Retry
                        </button>
                      )}
                      {(job.status === "queued" || job.status === "failed" || job.status === "dead_letter") && (
                        <button className="btn btn-danger" disabled={!!busy} onClick={async () => (await run("c" + job.id, () => api.cancelJob(job.id), "Job cancelled")) && reload()}>
                          Cancel
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
