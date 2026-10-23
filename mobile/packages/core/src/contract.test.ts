/**
 * Runs the client against a real, running CivicLoopAI backend, so the apps cannot drift from the API.
 * Skipped unless CIVICLOOP_CONTRACT_URL is set, for example:
 *   CIVICLOOP_CONTRACT_URL=http://127.0.0.1:8000 npm test
 * The backend must have the demo accounts from the test launcher (resident@civic.test, worker@civic.test, ...).
 */
import { describe, expect, it } from "vitest";
import { createApi } from "./api";

const url = process.env.CIVICLOOP_CONTRACT_URL;
const suite = url ? describe : describe.skip;

async function signedIn(email: string, password: string) {
  let token: string | null = null;
  const api = createApi({ baseUrl: () => url!, getToken: () => token });
  token = (await api.login(email, password)).access_token;
  return api;
}

suite("against a live backend", () => {
  it("answers its health check", async () => {
    expect(await createApi({ baseUrl: () => url!, getToken: () => null }).ping()).toBe(true);
  });

  it("lets a resident sign in, see who they are, and list only their own reports", async () => {
    const api = await signedIn("resident@civic.test", "resident-pass-1234");
    const me = await api.me();
    expect(me.role).toBe("reporter");
    expect(me.city).toBeTruthy();
    const reports = await api.listIncidents();
    expect(reports.every((r) => r.reporter_id === me.id)).toBe(true);
  });

  it("creates a report and reads it back with its pincode", async () => {
    const api = await signedIn("resident@civic.test", "resident-pass-1234");
    const made = await api.createIncident({
      reporter_type: "resident",
      description: "Contract test: bags of waste by the gate",
      latitude: 30.7333,
      longitude: 76.7794,
      occurred_at: new Date().toISOString(),
      pincode: "160017",
    });
    expect(made.status).toBe("pending_analysis");
    expect((await api.getIncident(made.id)).pincode).toBe("160017");
    expect(await api.listMedia(made.id)).toEqual([]);
  });

  it("gives a crew member their jobs and vehicles, and refuses a resident the same", async () => {
    const crew = await signedIn("worker@civic.test", "worker-pass-123456");
    expect((await crew.me()).role).toBe("sanitation_worker");
    expect(Array.isArray(await crew.listOrders())).toBe(true);
    expect(Array.isArray(await crew.myVehicles())).toBe(true);
    const resident = await signedIn("resident@civic.test", "resident-pass-1234");
    await expect(resident.myVehicles()).rejects.toMatchObject({ status: 403 });
  });

  it("suggests only confirmed cities, and needs a few letters", async () => {
    const api = createApi({ baseUrl: () => url!, getToken: () => null });
    expect(await api.cities("c")).toEqual([]);
  });
});
