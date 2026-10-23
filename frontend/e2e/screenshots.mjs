// Signs in as each role, visits every page and saves a full-page screenshot.
// Usage: node e2e/screenshots.mjs <output-dir>   (frontend on :3000, backend on :8000)
import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const BASE = process.env.BASE_URL ?? "http://localhost:3000";
const API = process.env.API_URL ?? "http://localhost:8000/api/v1";
const OUT = path.resolve(process.argv[2] ?? "../docs/screenshots");
fs.mkdirSync(OUT, { recursive: true });

const CREDS = {
  resident: { email: "resident@civic.test", password: "resident-pass-1234" },
  worker: { email: "worker@civic.test", password: "worker-pass-123456" },
  supervisor: { email: "supervisor@civic.test", password: "supervisor-pass-123" },
  admin: { email: "admin@civic.test", password: "admin-pass-12345" },
};

async function token(role) {
  const r = await fetch(`${API}/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(CREDS[role]) });
  return (await r.json()).access_token;
}
const get = async (role, p) => (await fetch(`${API}${p}`, { headers: { Authorization: `Bearer ${await token(role)}` } })).json();

const incidents = await get("supervisor", "/incidents?limit=200");
const reviewed = incidents.find((i) => i.status === "ready_for_review") ?? incidents[0];
const verified = incidents.find((i) => i.status === "verified");
const routes = await get("supervisor", "/routes");
const mine = (await get("resident", "/incidents"))[0];

const browser = await chromium.launch();
const written = [];

async function session(role, viewport = { width: 1440, height: 900 }) {
  const ctx = await browser.newContext({ viewport, permissions: ["geolocation"], geolocation: { latitude: 30.7398, longitude: 76.7827, accuracy: 20 } });
  const page = await ctx.newPage();
  if (role) {
    await page.goto(`${BASE}/login`);
    await page.getByLabel("Email").fill(CREDS[role].email);
    await page.getByLabel("Password").fill(CREDS[role].password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await page.waitForURL((u) => !u.pathname.startsWith("/login"));
  }
  return { page, ctx };
}

async function snap(page, group, name, url, after) {
  if (url) await page.goto(`${BASE}${url}`);
  await page.waitForLoadState("networkidle").catch(() => {});
  if (after) await after(page);
  await page.waitForTimeout(1500); // map tiles, charts and entrance animations
  const dir = path.join(OUT, group);
  fs.mkdirSync(dir, { recursive: true });
  const file = path.join(dir, `${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  written.push(path.relative(OUT, file).replaceAll("\\", "/"));
}

// signed out
{
  const { page, ctx } = await session(null);
  await snap(page, "00-public", "login", "/login");
  await snap(page, "00-public", "register", "/register");
  await ctx.close();
}

// resident
{
  const { page, ctx } = await session("resident");
  await snap(page, "01-resident", "my-reports", "/incidents");
  await snap(page, "01-resident", "report-an-incident", "/incidents/new");
  if (mine) await snap(page, "01-resident", "report-detail", `/incidents/${mine.id}`);
  await ctx.close();
}

// worker
{
  const { page, ctx } = await session("worker");
  await snap(page, "02-worker", "incidents", "/incidents");
  await snap(page, "02-worker", "my-assignments", "/work");
  await ctx.close();
}

// supervisor
{
  const { page, ctx } = await session("supervisor");
  await snap(page, "03-supervisor", "dashboard", "/");
  await snap(page, "03-supervisor", "incidents", "/incidents");
  await snap(page, "03-supervisor", "report-an-incident", "/incidents/new");
  await snap(page, "03-supervisor", "incident-detail", `/incidents/${reviewed.id}`);
  if (verified) await snap(page, "03-supervisor", "incident-detail-verified", `/incidents/${verified.id}`);
  await snap(page, "03-supervisor", "work-orders", "/work");
  await snap(page, "03-supervisor", "routes-planner", "/routes");
  if (routes[0]) await snap(page, "03-supervisor", "route-detail", `/routes/${routes[0].id}`);
  await snap(page, "03-supervisor", "insights-evaluations", "/insights");
  for (const tab of ["Pilots", "Models"]) {
    await snap(page, "03-supervisor", `insights-${tab.toLowerCase()}`, "/insights", async (p) => p.getByRole("tab", { name: tab }).click());
  }
  await snap(page, "03-supervisor", "integrations", "/integrations");
  await snap(page, "03-supervisor", "audit-log", "/admin/audit");
  await ctx.close();
}

// admin
{
  const { page, ctx } = await session("admin");
  await snap(page, "04-admin", "dashboard", "/");
  await snap(page, "04-admin", "users", "/admin/users");
  await snap(page, "04-admin", "cities", "/platform/cities");
  await snap(page, "04-admin", "background-jobs", "/admin/jobs");
  await ctx.close();
}

// phone view of the main pages
{
  const { page, ctx } = await session("supervisor", { width: 390, height: 844 });
  await snap(page, "05-phone", "dashboard", "/");
  await snap(page, "05-phone", "incidents", "/incidents");
  await snap(page, "05-phone", "report-an-incident", "/incidents/new");
  await snap(page, "05-phone", "routes-planner", "/routes");
  await ctx.close();
}

await browser.close();
console.log(`${written.length} screenshots in ${OUT}`);
console.log(written.join("\n"));
