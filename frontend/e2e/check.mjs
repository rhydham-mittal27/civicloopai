// Pass 2: drives every CivicLoop page, per role, against the real backend (real Gemini).
// Usage: node e2e/check.mjs  (backend on :8000 seeded by seed.sh, frontend on :3000)
import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const BASE = process.env.BASE_URL ?? "http://localhost:3000";
const API = process.env.API_URL ?? "http://localhost:8000/api/v1";
const OUT = process.env.SHOTS ?? path.resolve("e2e/shots");
const BEFORE = process.env.BEFORE_PNG;
const AFTER = process.env.AFTER_PNG;
fs.mkdirSync(OUT, { recursive: true });

const CREDS = {
  admin: { email: "admin@civic.test", password: "admin-pass-12345" },
  supervisor: { email: "supervisor@civic.test", password: "supervisor-pass-123" },
  worker: { email: "worker@civic.test", password: "worker-pass-123456" },
  resident: { email: "resident@civic.test", password: "resident-pass-1234" },
};
const NAV = {
  resident: ["My reports"],
  worker: ["Incidents", "My assignments"],
  supervisor: ["Dashboard", "Incidents", "Work orders", "Routes", "Insights", "Integrations", "Audit log"],
  admin: ["Dashboard", "Incidents", "Work orders", "Routes", "Insights", "Integrations", "Audit log", "Users", "Cities", "Background jobs"],
};
const ALL_PAGES = ["/work", "/routes", "/insights", "/integrations", "/admin/audit", "/admin/users", "/admin/jobs", "/platform/cities"];
const ALLOWED = {
  resident: [],
  worker: ["/work"],
  supervisor: ["/work", "/routes", "/insights", "/integrations", "/admin/audit"],
  admin: ALL_PAGES,
};

const failures = [];
let passed = 0;
const ok = (cond, name, extra = "") => {
  if (cond) {
    passed++;
    console.log(`  ok    ${name}`);
  } else {
    failures.push(`${name}${extra ? " :: " + extra : ""}`);
    console.log(`  FAIL  ${name}${extra ? " :: " + extra : ""}`);
  }
};
async function step(name, fn) {
  console.log(`\n# ${name}`);
  try {
    await fn();
  } catch (error) {
    const at = (String(error.stack).split("\n").find((l) => l.includes("check.mjs")) ?? "").trim().replace(/^.*check\.mjs/, "check.mjs");
    failures.push(`${name} threw :: ${String(error.message).split("\n")[0]} @ ${at}`);
    console.log(`  FAIL  threw: ${String(error.message).split("\n")[0]}`);
  }
}

const browser = await chromium.launch();
const bad = [];
async function newPage(viewport, tag) {
  const context = await browser.newContext({ viewport, permissions: ["geolocation"], geolocation: { latitude: 30.7333, longitude: 76.7794 } });
  const page = await context.newPage();
  page.on("pageerror", (e) => bad.push(`[${tag}] pageerror ${e.message}`));
  page.on("console", (m) => {
    if (m.type() === "error" && !/Failed to load resource/.test(m.text())) {
      const diff = m.text().split(String.fromCharCode(10)).filter((l) => /^\s*[+-] |<input|<form|<html|<body|<div|attributes/.test(l));
      bad.push(`[${tag}] [${page.url()}] console ${diff.length ? diff.join(" | ").slice(0, 700) : m.text().slice(0, 300)}`);
    }
  });
  page.on("response", (r) => {
    if (r.status() >= 500) bad.push(`[${tag}] ${r.status()} ${r.url()}`);
  });
  page.tag = tag;
  return page;
}
const shot = (page, name) => page.screenshot({ path: path.join(OUT, `${page.tag}-${name}.png`), fullPage: true });
const noScroll = async (page, name) =>
  ok(!(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1)), `${name}: no horizontal scroll`);

async function login(page, role) {
  await page.goto(`${BASE}/login`);
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await page.getByLabel("Email").fill(CREDS[role].email);
  await page.getByLabel("Password").fill(CREDS[role].password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL(role === "supervisor" || role === "admin" ? `${BASE}/` : `${BASE}/incidents`);
  await page.getByRole("heading", { level: 1 }).first().waitFor();
}
async function navItems(page) {
  return (await page.locator(".side-nav a .side-text").allInnerTexts()).map((t) => t.trim());
}
async function locked(page, role) {
  for (const p of ALL_PAGES.filter((p) => !ALLOWED[role].includes(p))) {
    await page.goto(`${BASE}${p}`);
    await page.getByRole("heading", { name: "This page is not available to your role" }).waitFor({ timeout: 8000 });
  }
  ok(true, `${role}: ${ALL_PAGES.length - ALLOWED[role].length} restricted pages show "not available to your role"`);
}
async function apiToken(role) {
  const r = await fetch(`${API}/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(CREDS[role]) });
  return (await r.json()).access_token;
}
async function apiReport(token, description, lat, lon, photo) {
  const r = await fetch(`${API}/incidents`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ reporter_type: "resident", description, latitude: lat, longitude: lon, occurred_at: new Date().toISOString() }),
  });
  const incident = await r.json();
  const form = new FormData();
  form.append("file", new Blob([fs.readFileSync(photo)], { type: "image/png" }), "site.png");
  await fetch(`${API}/incidents/${incident.id}/media`, { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form });
  return incident.id;
}

const desktop = { width: 1366, height: 820 };
const state = {};

/* ============================================================ auth pages */
const anon = await newPage(desktop, "desktop-anon");
await step("Auth pages", async () => {
  await anon.goto(`${BASE}/login`);
  await anon.getByRole("button", { name: "Sign in" }).waitFor();
  await shot(anon, "login");
  await anon.getByLabel("Email").fill(CREDS.supervisor.email);
  await anon.getByLabel("Password").fill("not-the-password-1");
  await anon.getByRole("button", { name: "Sign in" }).click();
  await anon.locator(".alert").waitFor();
  ok((await anon.locator(".alert").innerText()).includes("Invalid credentials"), "login: wrong password shows an error");
  await shot(anon, "login-error");

  await anon.goto(`${BASE}/register`);
  await shot(anon, "register");
  await anon.getByLabel("Full name").fill("Dup Person");
  await anon.getByLabel("Email").fill(CREDS.resident.email);
  await anon.getByLabel("Password").fill("some-long-password-1");
  await anon.getByLabel("City").fill("Chandigarh");
  await anon.getByLabel("Pincode").fill("160017");
  await anon.getByRole("button", { name: "Create account" }).click();
  await anon.locator(".alert").waitFor();
  ok((await anon.locator(".alert").innerText()).toLowerCase().includes("already"), "register: duplicate email shows an error");

  await anon.goto(`${BASE}/register`);
  await anon.getByLabel("Full name").fill("Fresh Reporter");
  await anon.getByLabel("Email").fill(`fresh${Date.now()}@civic.test`);
  await anon.getByLabel("Password").fill("fresh-reporter-pass-1");
  const NEW_CITY = `Newtown${Date.now()}`;
  await anon.getByLabel("City").fill(NEW_CITY);
  await anon.getByLabel("Pincode").fill("411001");
  ok((await anon.locator(".hint").allInnerTexts()).some((t) => t.includes("new here")), "register: an unknown city is announced as new");
  await anon.getByRole("button", { name: "Create account" }).click();
  await anon.waitForURL(`${BASE}/incidents`);
  ok((await navItems(anon)).join() === NAV.resident.join(), "register: new account lands signed in as a reporter");
  await anon.locator(".side-who").getByText(NEW_CITY).waitFor();
  ok(true, "tenancy: the sidebar names the person's city");
  await anon.waitForTimeout(800);
  ok((await anon.locator(".inc-row, .inc-card, table tbody tr").count()) === 0, "tenancy: a new city starts with none of Chandigarh's reports");

  await anon.evaluate(() => localStorage.clear());
  for (const p of ["/", "/work", "/incidents/new", "/admin/users"]) {
    await anon.goto(`${BASE}${p}`);
    await anon.waitForURL(/\/login/);
  }
  ok(true, "signed-out visits redirect to /login");
});

/* ============================================================ resident */
const res = await newPage(desktop, "desktop-resident");
await step("Resident: report an incident", async () => {
  await login(res, "resident");
  ok((await res.getByRole("heading", { level: 1 }).first().innerText()) === "My reports", "home is titled My reports");
  ok((await navItems(res)).join() === NAV.resident.join(), "nav shows only reporter links", (await navItems(res)).join());
  await shot(res, "home");

  await res.getByRole("link", { name: "Report incident" }).first().click();
  await res.waitForURL(/incidents\/new/);
  await shot(res, "report-blank");
  await res.getByRole("button", { name: "Submit report" }).click();
  await res.getByText("Tell us what you saw").waitFor();
  await res.getByText("Choose where it is").waitFor();
  ok(true, "report: an empty form is blocked with a clear message for each missing part");
  await res.getByRole("button", { name: "Overflowing bins" }).click();
  ok((await res.getByLabel("What did you see?").inputValue()) === "Overflowing bins", "report: a quick suggestion fills the description");
  await res.getByLabel("What did you see?").fill("Overflowing bins and loose debris behind the Sector 17 market");
  await res.getByRole("button", { name: "Use my location" }).click();
  await res.waitForFunction(() => document.getElementById("lat").value !== "");
  ok((await res.locator("#lat").inputValue()).startsWith("30.73"), "report: browser location fills the coordinates");
  await res.locator("#photo-input").setInputFiles(BEFORE);
  await res.getByAltText("Attached photo 1").waitFor();
  ok((await res.locator(".checklist li[data-done]").count()) === 3, "report: the checklist ticks off what, where and photo");
  await shot(res, "report-filled");
  await res.getByRole("button", { name: "Submit report" }).click();
  await res.waitForURL(/incidents\/[0-9a-f-]{36}/);
  state.incidentUrl = res.url();
  state.incidentId = state.incidentUrl.split("/").pop();
  await res.locator('img[alt="Before cleanup"]').waitFor();
  await res.waitForFunction(() => document.querySelector('img[alt="Before cleanup"]')?.naturalWidth > 0);
  ok(true, "report: lands on the incident with its photo rendered");
  ok((await res.locator('aside[aria-label="Actions"]').count()) === 0, "detail: reporter gets no staff panel");
  ok((await res.getByText("Nearby sensors").count()) === 0 && (await res.getByText("Possible duplicates").count()) === 0, "detail: reporter does not see staff sections");
  await shot(res, "detail");
  await noScroll(res, "resident detail");

  await res.goto(`${BASE}/`);
  await res.getByText("Overflowing bins and loose debris").first().waitFor();
  ok(true, "home lists the reporter's own report");
  await locked(res, "resident");
  await res.goto(`${BASE}/incidents/00000000-0000-0000-0000-000000000000`);
  await res.getByRole("heading", { name: "Incident not found" }).waitFor();
  ok(true, "unknown incident shows the not-found state");
});

// A second, nearby report from the same resident, to exercise duplicate detection and background jobs.
await step("Seed a nearby twin report via API", async () => {
  const token = await apiToken("resident");
  state.twinId = await apiReport(token, "Overflowing bins and loose debris behind the Sector 17 market", 30.7334, 76.7795, BEFORE);
  ok(!!state.twinId, "twin report created");
});

/* ============================================================ supervisor */
const sup = await newPage(desktop, "desktop-supervisor");
await step("Supervisor: analyse, rank and open a work order", async () => {
  await login(sup, "supervisor");
  ok((await sup.getByRole("heading", { level: 1 }).first().innerText()) === "Command center", "supervisor lands on the command center");
  ok((await navItems(sup)).join() === NAV.supervisor.join(), "nav shows supervisor links", (await navItems(sup)).join());
  await locked(sup, "supervisor");

  await sup.goto(state.incidentUrl);
  await sup.getByRole("button", { name: "Run analysis" }).click();
  await sup.getByText("The AI suggests").waitFor({ timeout: 90000 });
  ok(true, "real Gemini analysis comes back");
  await sup.getByText("Hotspot risk").waitFor();
  await sup.locator(".risk-big .risk").waitFor();
  ok(true, "risk score is calculated automatically after analysis");
  await shot(sup, "detail-analysed");
  await noScroll(sup, "supervisor detail");

  await sup.goto(`${BASE}/`);
  await sup.getByRole("heading", { name: "Command center" }).waitFor();
  await sup.locator(".pin").first().waitFor();
  const kpiTops = await sup.locator(".kpi").evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().top)));
  ok(kpiTops.length === 5 && new Set(kpiTops).size === 1, "dashboard: five compact KPI cards in a single row", kpiTops.join(","));
  const legend = (await sup.locator(".sightings-legend .chip").allInnerTexts()).join(" | ");
  ok(/Pending analysis/.test(legend) && /Ready for review/.test(legend) && /Approved/.test(legend), "dashboard: the map legend names pending, ready and approved", legend.replace(/\n/g, " "));
  await sup.locator(".pin").first().click();
  await sup.locator(".sightings-card").getByRole("link", { name: "Open report" }).waitFor();
  ok(true, "dashboard: selecting a map marker opens its details");
  await sup.locator(".attention-row").first().click();
  ok((await sup.locator(".attention-row[aria-pressed='true']").count()) === 1, "dashboard: choosing an item in the attention list highlights it");
  await shot(sup, "dashboard");
  await noScroll(sup, "dashboard");

  await sup.goto(`${BASE}/incidents`);
  await sup.getByRole("tab", { name: /Ready for review/ }).click();
  await sup.locator(".irow .risk").first().waitFor();
  ok(true, "incident list: ready-for-review reports show their risk");
  await sup.getByPlaceholder("Search by description or ID").fill("zzz-no-such-report");
  await sup.getByText("No reports match your search").waitFor();
  await sup.getByPlaceholder("Search by description or ID").fill("");
  ok(true, "incident list: search narrows and clears");
  await shot(sup, "queue-ranked");
  await noScroll(sup, "incident list");

  await sup.goto(state.incidentUrl);
  await sup.getByRole("button", { name: "Create work order" }).click();
  await sup.getByRole("button", { name: "Approve for cleanup" }).first().click();
  await sup.getByText("Assign worker").first().waitFor();
  await sup.getByLabel("Assign to").selectOption({ label: "Karan Singh" });
  await sup.getByRole("button", { name: "Assign worker" }).click();
  await sup.getByText("Karan Singh").first().waitFor();
  ok(true, "work order created, approved and assigned");
  await sup.getByLabel("Override priority").fill("9");
  await sup.getByLabel("Reason").fill("Next to the market entrance");
  await sup.getByRole("button", { name: "Apply override" }).click();
  await sup.getByText("Override: Next to the market entrance").waitFor();
  ok(true, "priority override requires and records a reason");
  await shot(sup, "detail-ordered");
});

await step("Supervisor: work orders page", async () => {
  await sup.goto(`${BASE}/work`);
  await sup.getByRole("heading", { name: "Work orders" }).waitFor();
  await sup.getByText("Overflowing bins").first().waitFor();
  await shot(sup, "work");
  await noScroll(sup, "work orders");
  await sup.getByRole("tab", { name: "Assigned" }).click();
  await sup.getByText("Overflowing bins").first().waitFor();
  ok(true, "work orders filter by status");
});

await step("Supervisor: routes", async () => {
  await sup.goto(`${BASE}/routes`);
  await sup.getByRole("heading", { name: "Route planner" }).waitFor();
  await sup.locator(".joblist .job").first().locator("input").check();
  await shot(sup, "routes");
  await noScroll(sup, "route planner");
  await sup.getByRole("button", { name: "Preview optimised route" }).click();
  await sup.locator(".preview-card").waitFor();
  ok((await sup.locator(".preview-stops li").count()) === 1, "planner: a preview shows the route before anything is saved");
  await sup.getByRole("button", { name: "Save route" }).click();
  await sup.waitForURL(/routes\/[0-9a-f-]{36}/);
  await sup.getByRole("heading", { name: "Stops in order" }).waitFor();
  ok((await sup.locator(".stops li").count()) === 1, "route detail lists the stop");
  await sup.getByRole("button", { name: "Approve route" }).click();
  await sup.getByText("Approved", { exact: true }).first().waitFor();
  ok(true, "route can be approved");
  await shot(sup, "route-detail");
  await sup.goto(`${BASE}/routes`);
  await sup.getByText("Planned routes").waitFor();
  await sup.locator(".route-card", { hasText: "Approved" }).first().waitFor();
  ok(true, "route appears in the list as approved");
});

await step("Supervisor: OR-Tools route over several stops", async () => {
  const supToken = await apiToken("supervisor");
  const resToken = await apiToken("resident");
  const auth = { "Content-Type": "application/json", Authorization: `Bearer ${supToken}` };
  const stops = [
    ["Route stop A, bins at the bus stop", 30.7001, 76.7701],
    ["Route stop B, debris at the school wall", 30.7122, 76.7655],
    ["Route stop C, waste at the petrol pump", 30.7254, 76.7810],
    ["Route stop D, bags at the temple road", 30.7390, 76.7702],
  ];
  for (const [text, lat, lon] of stops) {
    const id = await apiReport(resToken, text, lat, lon, BEFORE);
    await fetch(`${API}/incidents/${id}/analysis`, { method: "POST", headers: auth });
    const order = await (await fetch(`${API}/incidents/${id}/work-orders`, { method: "POST", headers: auth, body: JSON.stringify({ priority: 20, estimated_volume: 1 }) })).json();
    await fetch(`${API}/work-orders/${order.id}/approve`, { method: "POST", headers: auth });
  }
  await sup.goto(`${BASE}/routes`);
  await sup.getByRole("heading", { name: "Route planner" }).waitFor();
  for (const [text] of stops) await sup.locator(".joblist .job", { hasText: text }).locator("input").check();
  await sup.getByLabel("Longest drive (min)").fill("1");
  await sup.getByRole("button", { name: "Preview optimised route" }).click();
  await sup.locator(".alert").waitFor();
  ok(/limit/.test(await sup.locator(".alert").innerText()), "route: an impossible drive-time limit is refused with a clear message");
  await sup.getByLabel("Longest drive (min)").fill("600");
  await sup.getByRole("button", { name: "Preview optimised route" }).click();
  await sup.locator(".preview-card").waitFor();
  ok((await sup.locator(".preview-stops li").count()) === 4, "planner: the preview lists all four stops in optimised order");
  await sup.getByRole("button", { name: "Save route" }).click();
  await sup.waitForURL(/routes\/[0-9a-f-]{36}/);
  await sup.getByText("Optimised with Google OR-Tools").waitFor();
  await sup.getByText("Limited to 600 min").waitFor();
  ok((await sup.locator(".stops li").count()) === 4, "route: OR-Tools plan lists all four stops, with its limit and solver");
  await sup.getByRole("heading", { name: "Route map" }).waitFor();
  ok((await sup.locator(".gframe iframe").count()) === 1 && /maps\.google\.com|google\.com\/maps/.test((await sup.locator(".gframe iframe").getAttribute("src")) ?? ""), "route map: the Google Maps iframe is the default view");
  await sup.getByText("Optimisation view", { exact: true }).click();
  await sup.getByText("Nearest-neighbour", { exact: true }).waitFor();
  ok(true, "route: nearest-neighbour length shown for comparison");
  ok((await sup.locator(".routemap .stop").count()) === 4, "route map: one numbered marker per stop");
  await sup.getByText("vs nearest-neighbour", { exact: true }).click();
  await sup.locator(".routemap .base-line").waitFor();
  ok(true, "route map: comparison overlay draws the nearest-neighbour path");
  await sup.getByText("vs selection order", { exact: true }).click();
  await sup.locator(".routemap .base-line").waitFor();
  await sup.getByRole("button", { name: "Replay" }).click();
  await sup.locator(".routemap .stop").first().hover();
  ok((await sup.locator(".routemap-readout").innerText()).includes("Stop 1"), "route map: hovering a stop shows its details");
  await noScroll(sup, "route map");
  await shot(sup, "route-ortools");
  await noScroll(sup, "route detail");
});

await step("Supervisor: duplicates, sensors, background analysis", async () => {
  await sup.goto(`${BASE}/incidents/${state.twinId}`);
  await sup.getByRole("heading", { name: "Possible duplicates" }).waitFor();
  await sup.getByText("% match").first().waitFor();
  const chips = await sup.locator(".why-chips").first().innerText();
  ok(/near/.test(chips) && /(meaning|words)/.test(chips), "duplicates: each candidate explains why it matched", chips.replace(/\n/g, " | "));
  await sup.locator('.asset input[type="checkbox"]').first().check();
  await sup.getByRole("button", { name: "Group selected as duplicates" }).click();
  await sup.getByText("Suggested group").waitFor();
  await sup.getByRole("button", { name: "Confirm duplicates" }).click();
  await sup.getByText("Confirmed duplicate group").waitFor();
  ok(true, "duplicate candidate found, grouped and confirmed");
  await shot(sup, "detail-duplicates");

  // Background AI job on the twin (worker thread inside the API).
  await sup.getByRole("button", { name: "Queue as background job" }).click();
  await sup.getByText("The AI suggests").waitFor({ timeout: 90000 });
  ok(true, "background analysis job completes and the result appears");

  await sup.goto(`${BASE}/integrations`);
  await sup.getByLabel("Sensor ID").fill("bin-s17-04");
  await sup.getByLabel("Latitude").fill("30.7333");
  await sup.getByLabel("Longitude").fill("76.7794");
  await sup.getByLabel("Value").fill("0.9");
  await sup.getByRole("button", { name: "Record reading" }).click();
  await sup.getByRole("cell", { name: "bin-s17-04" }).first().waitFor();
  await sup.getByLabel("Latest reading for a sensor").fill("bin-s17-04");
  await sup.getByRole("button", { name: "Look up" }).click();
  await sup.getByText("fill_level 0.9").first().waitFor();
  ok(true, "sensor reading recorded and looked up");
  await sup.getByLabel(/Incident ID to link/).first().fill(state.incidentId);
  await sup.getByRole("button", { name: "Link", exact: true }).first().click();
  await sup.getByText(`#${state.incidentId.slice(0, 8)}`).first().waitFor();
  ok(true, "sensor linked to an incident");
  await shot(sup, "integrations-sensors");
  await noScroll(sup, "integrations");

  await sup.goto(state.incidentUrl);
  await sup.getByRole("heading", { name: "Nearby sensors" }).waitFor();
  await sup.getByText("Linked", { exact: true }).waitFor();
  ok(true, "linked sensor shows on the incident");

  await sup.goto(`${BASE}/integrations`);
  await sup.getByRole("tab", { name: "Municipal system" }).click();
  await sup.getByLabel(/Export order/).first().check();
  await sup.getByRole("button", { name: /Export/ }).click();
  await sup.getByText("civicloop-work-orders-v1").waitFor();
  ok(true, "municipal export produces a payload");
  await shot(sup, "integrations-municipal");
});

await step("Supervisor: insights", async () => {
  await sup.goto(`${BASE}/insights`);
  await sup.getByRole("button", { name: "Run evaluation on live data" }).click();
  await sup.getByText("Reports received").first().waitFor();
  await sup.getByRole("button", { name: "Compare with baseline" }).first().click();
  await sup.getByRole("columnheader", { name: "Baseline" }).waitFor();
  ok(true, "evaluation runs on live data and compares with baseline");
  await shot(sup, "insights-evaluations");
  await noScroll(sup, "insights");

  await sup.getByRole("tab", { name: "Pilots" }).click();
  const start = new Date();
  const end = new Date(start.getTime() + 70 * 86400000);
  const iso = (d) => d.toISOString().slice(0, 10);
  await sup.getByLabel("Name").fill("Chandigarh Sector 17");
  await sup.getByLabel("Location").fill("Sector 17, Chandigarh");
  await sup.getByLabel("Starts").fill(iso(start));
  await sup.getByLabel("Ends").fill(iso(end));
  await sup.getByLabel("Baseline version").fill("q3-2026-manual");
  await sup.getByRole("button", { name: "Start pilot" }).click();
  await sup.getByRole("heading", { name: "Chandigarh Sector 17" }).waitFor();
  await sup.getByLabel("Metric").first().fill("resolution_hours");
  await sup.getByLabel("Value").first().fill("18");
  await sup.getByRole("button", { name: "Record" }).first().click();
  await sup.getByText("resolution hours").waitFor();
  ok(true, "pilot started and a metric recorded");
  await shot(sup, "insights-pilots");
});

/* ============================================================ worker */
const wrk = await newPage(desktop, "desktop-worker");
await step("Worker: assignment, evidence", async () => {
  await login(wrk, "worker");
  ok((await wrk.getByRole("heading", { level: 1 }).first().innerText()) === "Incidents", "worker lands on the incident list");
  ok((await navItems(wrk)).join() === NAV.worker.join(), "nav shows worker links", (await navItems(wrk)).join());
  await locked(wrk, "worker");

  await wrk.goto(`${BASE}/work`);
  await wrk.getByRole("heading", { name: "My assignments" }).waitFor();
  await wrk.getByText("Overflowing bins").first().waitFor();
  ok((await wrk.getByRole("tab").count()) > 0, "assignments page loads for the worker");
  await shot(wrk, "work");
  await noScroll(wrk, "worker assignments");
  await wrk.getByRole("button", { name: "Start" }).click();
  await wrk.getByRole("button", { name: "Complete" }).waitFor();
  await wrk.getByRole("button", { name: "Complete" }).click();
  await wrk.getByRole("link", { name: "Send evidence" }).waitFor();
  ok(true, "worker starts and completes the job");
  await wrk.getByRole("link", { name: "Send evidence" }).click();
  await wrk.waitForURL(/incidents\//);
  await wrk.getByLabel("After-cleanup photo").setInputFiles(AFTER);
  await wrk.getByLabel("Notes").fill("Bins emptied and street swept");
  await wrk.getByRole("button", { name: "Submit evidence" }).click();
  await wrk.getByRole("heading", { name: "Cleanup verification" }).waitFor();
  ok((await wrk.getByText("Verified", { exact: true }).count()) > 0, "clear after-photo verifies by rule");
  await wrk.locator('img[alt="After cleanup"]').waitFor();
  await shot(wrk, "detail-verified");
  ok((await wrk.getByRole("button", { name: "Confirm cleaned" }).count()) === 0, "worker cannot review their own evidence");
});

await step("Supervisor: review evidence", async () => {
  await sup.goto(state.incidentUrl);
  await sup.getByRole("heading", { name: "Cleanup verification" }).waitFor();
  await sup.getByLabel("Review reason").fill("Bags still visible in the corner");
  await sup.getByRole("button", { name: "Send back to field" }).click();
  await sup.getByText("In progress", { exact: true }).first().waitFor();
  ok(true, "supervisor can overturn the rule check and send the job back");
  await sup.getByRole("heading", { name: "History" }).waitFor();
  ok((await sup.locator(".timeline li").count()) >= 5, "history lists who did what");
  await shot(sup, "detail-history");

  await sup.goto(`${BASE}/admin/audit`);
  await sup.getByRole("heading", { name: "Audit log" }).waitFor();
  await sup.getByRole("cell", { name: "approved", exact: true }).first().waitFor();
  await shot(sup, "audit");
  await sup.getByLabel("Show").selectOption("work_order");
  await sup.getByRole("cell", { name: "work order", exact: false }).first().waitFor();
  ok(true, "audit log lists actions and filters by type");
});

/* ============================================================ admin */
const adm = await newPage(desktop, "desktop-admin");
await step("Admin: users, jobs, everything reachable", async () => {
  await login(adm, "admin");
  ok((await navItems(adm)).join() === NAV.admin.join(), "nav shows every link", (await navItems(adm)).join());

  await adm.goto(`${BASE}/admin/users`);
  await adm.getByRole("heading", { name: "All accounts" }).waitFor();
  const temp = `temp${Date.now()}@civic.test`;
  await adm.getByLabel("Full name").fill("Temp Worker");
  await adm.getByLabel("Email").fill(temp);
  await adm.getByLabel("Temporary password").fill("temp-worker-pass-1");
  await adm.getByLabel("Pincode").fill("160017");
  await adm.getByLabel("Role", { exact: true }).selectOption("sanitation_worker");
  await adm.getByRole("button", { name: "Create account" }).click();
  await adm.getByRole("cell", { name: temp }).waitFor();
  const row = adm.getByRole("row", { name: new RegExp(temp) });
  await row.getByRole("button", { name: "Deactivate" }).click();
  await row.getByRole("button", { name: "Reactivate" }).waitFor();
  ok(true, "admin creates a staff account and deactivates it");
  const self = adm.getByRole("row", { name: /Meera Admin/ });
  ok(await self.getByRole("button", { name: "Deactivate" }).isDisabled(), "admin cannot deactivate themselves");
  await shot(adm, "users");
  await noScroll(adm, "users");

  await adm.goto(`${BASE}/platform/cities`);
  await adm.getByRole("heading", { name: "Cities" }).waitFor();
  await adm.getByRole("cell", { name: /Chandigarh/ }).first().waitFor();
  const unconfirmed = adm.getByRole("row", { name: /Newtown/ }).first();
  await unconfirmed.getByText("Not confirmed").waitFor();
  await unconfirmed.getByRole("button", { name: "Confirm" }).click();
  await unconfirmed.getByText("Confirmed").waitFor();
  ok(true, "platform: a self-opened city is listed as not confirmed, and the platform admin confirms it");
  await shot(adm, "platform-cities");
  await noScroll(adm, "platform cities");

  await adm.goto(`${BASE}/admin/jobs`);
  await adm.getByRole("heading", { name: "Background jobs" }).waitFor();
  await adm.getByText("On (gemini)").waitFor();
  await adm.getByText("analyze incident").first().waitFor();
  ok(true, "jobs page shows system status and the background analysis job");
  await shot(adm, "jobs");
  await noScroll(adm, "jobs");

  await adm.goto(`${BASE}/insights`);
  await adm.getByRole("tab", { name: "Models" }).click();
  await adm.getByRole("heading", { name: "Risk scoring" }).waitFor();
  ok((await adm.getByText("Active: hand-set formula").count()) === 1, "models: formula is active before any training");
  await adm.getByRole("button", { name: "Train risk model now" }).click();
  await adm.getByText("of the training data is simulated").waitFor({ timeout: 90000 });
  ok(true, "models: training runs and the simulated-data warning is shown");
  await adm.getByRole("columnheader", { name: "Trained model" }).waitFor();
  await adm.getByRole("cell", { name: "AUC", exact: true }).waitFor();
  const deployed = (await adm.getByText(/^Deployed /).count()) > 0;
  ok(true, `models: metrics table compares model and formula (${deployed ? "model deployed" : "formula kept"})`);
  await adm.getByRole("heading", { name: "Duplicate detection" }).waitFor();
  await adm.getByRole("heading", { name: "Route planning" }).waitFor();
  await adm.getByText("Google OR-Tools").first().waitFor();
  await shot(adm, "insights-models");
  await noScroll(adm, "models");
  state.modelDeployed = deployed;

  // A fresh report is scored by whichever method is now active, and says which.
  const resToken2 = await apiToken("resident");
  const supToken2 = await apiToken("supervisor");
  const freshId = await apiReport(resToken2, "Dumped waste outside the community hall", 30.7155, 76.7455, BEFORE);
  await fetch(`${API}/incidents/${freshId}/risk`, { method: "POST", headers: { Authorization: `Bearer ${supToken2}` } });
  await adm.goto(`${BASE}/incidents/${freshId}`);
  await adm.getByRole("heading", { name: "Hotspot risk" }).waitFor();
  if (deployed) {
    await adm.getByText("Chance of another report within 500 m in the next 30 days.").waitFor();
    await adm.getByText("What moved this score").waitFor();
    ok(true, "risk: scored by the trained model, as a probability with the inputs that moved it");
  } else {
    await adm.getByText("It is not a probability.").waitFor();
    ok(true, "risk: formula kept, labelled as an index and not a probability");
  }
  await shot(adm, "detail-risk-model");

  for (const p of ALL_PAGES) {
    await adm.goto(`${BASE}${p}`);
    await adm.getByRole("heading", { level: 1 }).first().waitFor();
    const text = await adm.getByRole("heading", { level: 1 }).first().innerText();
    ok(!/not available/.test(text), `admin can open ${p}`);
  }
});

/* ============================================================ mobile sweep */
await step("Mobile sweep (390px): every page per role", async () => {
  for (const role of ["resident", "worker", "supervisor", "admin"]) {
    const m = await newPage({ width: 390, height: 844 }, `mobile-${role}`);
    await login(m, role);
    await noScroll(m, `${role} home`);
    await shot(m, "home");
    const pages = [...ALLOWED[role], "/incidents", "/incidents/new", `/incidents/${state.incidentId}`];
    for (const p of pages) {
      await m.goto(`${BASE}${p}`);
      await m.getByRole("heading", { level: 1 }).first().waitFor();
      await m.waitForTimeout(250);
      await noScroll(m, `${role} ${p.replace(state.incidentId, ":id")}`);
      await shot(m, p.replace(/\//g, "_").replace(state.incidentId, "id") || "root");
    }
    await m.context().close();
  }
});

await browser.close();
console.log(`\n${bad.length ? "Console/server problems:\n- " + [...new Set(bad)].join("\n- ") : "No console errors or 5xx responses."}`);
console.log(`\n${passed} checks passed, ${failures.length} failed.`);
if (failures.length) console.log("FAILURES:\n- " + failures.join("\n- "));
process.exit(failures.length || bad.length ? 1 : 0);
