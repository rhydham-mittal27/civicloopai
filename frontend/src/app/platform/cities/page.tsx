"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { useToast } from "@/components/Toast";
import { Empty, ErrorNote, Loading, PageHead, Spinner, formatWhen } from "@/components/ui";
import { api, setTenant, type CityRow } from "@/lib/api";
import { useAction, useLoad } from "@/lib/hooks";

export default function CitiesPage() {
  return (
    <AppShell roles={["admin"]}>
      <Cities />
    </AppShell>
  );
}

function Cities() {
  const me = useLoad(() => api.me(), []);
  const { data, error, loading, reload } = useLoad(() => api.platformCities(), []);
  const { busy, error: actionError, run } = useAction();
  const toast = useToast();
  const router = useRouter();
  const [mergeFrom, setMergeFrom] = useState<CityRow | null>(null);
  const [mergeInto, setMergeInto] = useState("");

  if (me.data && !me.data.is_platform_admin) {
    return (
      <>
        <PageHead title="Cities">This page is for the people who run the whole platform.</PageHead>
        <Empty title="Platform administrators only">Ask the operator of this deployment to add your email to CIVICLOOP_PLATFORM_ADMINS.</Empty>
      </>
    );
  }

  const others = (city: CityRow) => (data ?? []).filter((c) => c.id !== city.id);

  return (
    <>
      <PageHead title="Cities">
        Every city is a separate workspace. Confirm the ones that are real, and merge a misspelt city into the right one.
      </PageHead>
      <ErrorNote message={actionError} />
      {error ? (
        <ErrorNote message={error} />
      ) : loading || !data ? (
        <Loading />
      ) : data.length === 0 ? (
        <Empty title="No cities yet">The first person to register opens one.</Empty>
      ) : (
        <div className="table-wrap">
          <table className="tbl">
            <thead>
              <tr>
                <th>City</th>
                <th>People</th>
                <th>Reports</th>
                <th>Opened</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {data.map((c) => (
                <tr key={c.id}>
                  <td>
                    <strong>{c.name}</strong>
                    {c.state && <span className="muted"> · {c.state}</span>}
                  </td>
                  <td>{c.users}</td>
                  <td>{c.incidents}</td>
                  <td>{formatWhen(c.created_at)}</td>
                  <td>
                    <span className="badge" data-status={c.is_active ? (c.verified ? "verified" : "ready_for_review") : "rejected"}>
                      {!c.is_active ? "Disabled" : c.verified ? "Confirmed" : "Not confirmed"}
                    </span>
                  </td>
                  <td>
                    <div className="row-actions">
                      {!c.verified && (
                        <button
                          className="btn btn-sm"
                          disabled={!!busy}
                          onClick={async () => (await run(c.id, () => api.patchCity(c.id, { verified: true }), `${c.name} confirmed`)) && reload()}
                        >
                          {busy === c.id && <Spinner />}Confirm
                        </button>
                      )}
                      <button
                        className="btn btn-sm"
                        disabled={!!busy || c.id === me.data?.tenant_id}
                        title={c.id === me.data?.tenant_id ? "You are working in this city" : undefined}
                        onClick={async () => (await run(c.id, () => api.patchCity(c.id, { is_active: !c.is_active }), c.is_active ? `${c.name} disabled` : `${c.name} enabled`)) && reload()}
                      >
                        {c.is_active ? "Disable" : "Enable"}
                      </button>
                      <button
                        className="btn btn-sm"
                        disabled={!!busy || c.id === me.data?.tenant_id || data.length < 2}
                        onClick={() => {
                          setMergeFrom(c);
                          setMergeInto(others(c)[0]?.id ?? "");
                        }}
                      >
                        Merge into…
                      </button>
                      <button
                        className="btn btn-sm"
                        disabled={c.id === me.data?.tenant_id || !c.is_active}
                        onClick={() => {
                          setTenant(c.id);
                          router.push("/");
                        }}
                      >
                        Open
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {mergeFrom && (
        <form
          className="form form-wide"
          onSubmit={async (e) => {
            e.preventDefault();
            if (await run("merge", () => api.mergeCity(mergeFrom.id, mergeInto), `${mergeFrom.name} merged`)) {
              toast("Everything it held was moved");
              setMergeFrom(null);
              reload();
            }
          }}
        >
          <h2 className="h-sm">Merge {mergeFrom.name}</h2>
          <p className="muted">
            Its {mergeFrom.users} people and {mergeFrom.incidents} reports move to the city you pick, then {mergeFrom.name} is removed. This cannot be undone.
          </p>
          <div className="field form-narrow">
            <label htmlFor="merge-into">Merge into</label>
            <select id="merge-into" className="select" value={mergeInto} onChange={(e) => setMergeInto(e.target.value)}>
              {others(mergeFrom).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
          <div className="row-actions">
            <button className="btn btn-primary" disabled={!!busy || !mergeInto}>
              {busy === "merge" && <Spinner />}Merge cities
            </button>
            <button type="button" className="btn" onClick={() => setMergeFrom(null)}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </>
  );
}
