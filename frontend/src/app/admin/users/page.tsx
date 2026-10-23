"use client";

import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Empty, ErrorNote, Loading, PageHead, Spinner, formatWhen } from "@/components/ui";
import { api, ROLE_LABEL, ROLES, type Role } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useAction, useLoad } from "@/lib/hooks";

export default function UsersPage() {
  return (
    <AppShell roles={["admin"]}>
      <Users />
    </AppShell>
  );
}

function Users() {
  const { principal } = useAuth();
  const { data, error, loading, reload } = useLoad(() => api.listUsers(), []);
  const { busy, error: actionError, run } = useAction();
  const [form, setForm] = useState({ name: "", email: "", password: "", role: "sanitation_worker" as Role, pincode: "" });
  const me = useLoad(() => api.me(), []);

  return (
    <>
      <PageHead title="Users">Create staff accounts for {me.data?.city ?? "your city"} and manage who can do what.</PageHead>

      <form
        className="form form-wide"
        onSubmit={async (e) => {
          e.preventDefault();
          if (await run("create", () => api.register({ ...form, city: me.data?.city ?? "" }), "Account created")) {
            setForm({ ...form, name: "", email: "", password: "" });
            reload();
          }
        }}
      >
        <h2 className="h-sm">Create an account</h2>
        <div className="split">
          <div className="field">
            <label htmlFor="u-name">Full name</label>
            <input id="u-name" className="input" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          <div className="field">
            <label htmlFor="u-email">Email</label>
            <input id="u-email" className="input" type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </div>
          <div className="field">
            <label htmlFor="u-pass">Temporary password</label>
            <input id="u-pass" className="input" type="password" required minLength={12} autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
          </div>
          <div className="field">
            <label htmlFor="u-pin">Pincode{me.data?.city ? <span className="muted"> · {me.data.city}</span> : null}</label>
            <input id="u-pin" className="input mono" required inputMode="numeric" pattern="[1-9][0-9]{5}" maxLength={6} placeholder="160017" value={form.pincode} onChange={(e) => setForm({ ...form, pincode: e.target.value.replace(/\D/g, "") })} />
          </div>
          <div className="field">
            <label htmlFor="u-role">Role</label>
            <select id="u-role" className="select" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {ROLE_LABEL[r]}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div>
          <button className="btn btn-primary" disabled={!!busy}>
            {busy === "create" && <Spinner />}
            Create account
          </button>
        </div>
      </form>
      <ErrorNote message={actionError} />

      <section className="section" aria-labelledby="all-users">
        <h2 id="all-users">All accounts</h2>
        {error ? (
          <ErrorNote message={error} />
        ) : loading && !data ? (
          <Loading />
        ) : (data ?? []).length === 0 ? (
          <Empty title="No users" />
        ) : (
          <div className="table-wrap">
            <table className="tbl">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Pincode</th>
                  <th>Role</th>
                  <th>Joined</th>
                  <th>Access</th>
                </tr>
              </thead>
              <tbody>
                {(data ?? []).map((u) => {
                  const self = u.id === principal?.userId;
                  return (
                    <tr key={u.id} data-inactive={u.is_active ? undefined : ""}>
                      <td>
                        {u.name} {self && <span className="tag">You</span>}
                      </td>
                      <td>{u.email}</td>
                      <td className="mono">{u.pincode ?? "—"}</td>
                      <td>
                        <select
                          className="select select-sm"
                          aria-label={`Role for ${u.name}`}
                          value={u.role}
                          disabled={self || !!busy}
                          onChange={async (e) => {
                            if (await run(u.id, () => api.patchUser(u.id, { role: e.target.value as Role }), "Role updated")) reload();
                          }}
                        >
                          {ROLES.map((r) => (
                            <option key={r} value={r}>
                              {ROLE_LABEL[r]}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>{formatWhen(u.created_at)}</td>
                      <td>
                        <button
                          className={u.is_active ? "btn btn-danger" : "btn"}
                          disabled={self || !!busy}
                          onClick={async () => {
                            if (await run(u.id, () => api.patchUser(u.id, { is_active: !u.is_active }), u.is_active ? "Account deactivated" : "Account reactivated")) reload();
                          }}
                        >
                          {u.is_active ? "Deactivate" : "Reactivate"}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
