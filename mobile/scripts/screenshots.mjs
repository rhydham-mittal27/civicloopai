// Drives both mobile apps (their web exports, in a phone-sized browser) and saves a screenshot of every screen.
//   node mobile/scripts/screenshots.mjs <output-dir> <photo.png>
// Needs: backend on :8000 with the demo accounts, and preview servers on :8082 (resident) and :8083 (crew):
//   python mobile/scripts/preview_server.py <web-export-dir> 8082
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const { chromium } = createRequire(path.resolve(here, "../../frontend/package.json"))("@playwright/test");

const OUT = path.resolve(process.argv[2] ?? "../docs/mobile");
const PHOTO = path.resolve(process.argv[3] ?? "photo.png");
const API = "http://127.0.0.1:8000/api/v1";
const PHONE = { width: 390, height: 844 };
const TALL = { width: 390, height: 1500 };

async function apiToken(email, password) {
  const r = await fetch(`${API}/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) });
  return (await r.json()).access_token;
}

async function session(browser, base, name) {
  const context = await browser.newContext({
    viewport: PHONE,
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
    permissions: ["geolocation"],
    geolocation: { latitude: 30.7398, longitude: 76.7827, accuracy: 15 },
  });
  const page = await context.newPage();
  const problems = [];
  page.on("pageerror", (e) => problems.push(String(e)));
  page.on("console", (m) => m.type() === "error" && !/Failed to load resource|tile\.openstreetmap/.test(m.text()) && problems.push(m.text().slice(0, 200)));
  fs.mkdirSync(path.join(OUT, name), { recursive: true });
  const written = [];
  const snap = async (file, tall = false) => {
    if (tall) await page.setViewportSize(TALL);
    await page.waitForTimeout(900);
    await page.screenshot({ path: path.join(OUT, name, `${file}.png`) });
    if (tall) await page.setViewportSize(PHONE);
    written.push(`${name}/${file}.png`);
  };
  const field = (label) => page.getByLabel(label).locator("visible=true").first();
  // the tab bar comes last in the page, so its label is the last exact match of the text
  const tab = async (label) => {
    await page.getByText(label, { exact: true }).last().click();
    await page.waitForTimeout(600);
  };
  await page.goto(base);
  return { page, snap, tab, field, problems, written, context };
}

async function resident(browser) {
  const { page, snap, tab, field, problems, written } = await session(browser, "http://localhost:8082", "resident");
  await page.getByText("See waste? Report it").waitFor();
  await snap("00-welcome-1");
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByText("A person reviews every report").waitFor();
  await snap("00-welcome-2");
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByText("Follow it until it is clean").waitFor();
  await snap("00-welcome-3");
  await page.getByRole("button", { name: "Get started" }).click();
  await page.getByRole("button", { name: "Sign in" }).waitFor();
  await snap("01-sign-in");

  await page.getByRole("button", { name: "Create an account" }).click();
  await field("Full name").waitFor();
  await field("Full name").fill("Anita Sharma");
  await field("Email").fill("anita@example.com");
  await field("City").fill("Chandigarh");
  await field("Pincode").fill("160017");
  await snap("02-create-account", true);
  await page.goBack();

  await page.getByRole("button", { name: /Server:/ }).click();
  await page.getByRole("button", { name: "Test connection" }).click();
  await page.getByText(/Connected/).waitFor();
  await snap("03-server-address");
  await page.goBack();

  await field("Email").fill("resident@civic.test");
  await field("Password").fill("resident-pass-1234");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByText("My reports").first().waitFor();
  await page.waitForTimeout(2000);
  await snap("04-my-reports");

  await tab("Report");
  await page.getByText("Report waste").first().waitFor();
  await snap("05-report-empty", true);
  console.error("step: chips");
  await page.getByRole("button", { name: "Overflowing bins" }).click();
  await page.getByRole("button", { name: "Plastic litter" }).click();
  console.error("step: location");
  await page.getByRole("button", { name: "Use my location" }).click();
  await page.getByText(/Pin placed/).waitFor({ timeout: 15000 });
  console.error("step: gallery");
  const [chooser] = await Promise.all([page.waitForEvent("filechooser"), page.getByRole("button", { name: "From gallery" }).click()]);
  await chooser.setFiles(PHOTO);
  await page.getByLabel("Photo 1", { exact: true }).waitFor();
  await page.waitForTimeout(1500);
  await snap("06-report-filled", true);
  await page.getByRole("button", { name: "Submit report" }).click();
  await page.getByText("Photos", { exact: true }).first().waitFor({ timeout: 30000 });

  await page.waitForTimeout(1800);
  await snap("07-report-detail", true);
  await page.goBack();
  await tab("My reports");
  await page.waitForTimeout(1500);

  console.error("step: account");
  await tab("Account");
  await page.getByText("Sign out").first().waitFor();
  await snap("08-account");
  return { problems, written };
}

async function crew(browser) {
  const { page, snap, tab, field, problems, written } = await session(browser, "http://localhost:8083", "crew");
  await page.getByText("Your jobs, most urgent first").waitFor();
  await snap("00-welcome-1");
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByText("A route planned for you").waitFor();
  await snap("00-welcome-2");
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByText("Share location, send proof").waitFor();
  await snap("00-welcome-3");
  await page.getByRole("button", { name: "Get started" }).click();
  await page.getByRole("button", { name: "Sign in" }).waitFor();
  await snap("01-sign-in");
  await field("Email").fill("worker@civic.test");
  await field("Password").fill("worker-pass-123456");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByText("My jobs").first().waitFor();
  await page.getByText(/Priority \d+/).first().waitFor();
  await snap("02-jobs-todo");

  // the route the supervisor approved for this driver
  await page.getByText("Your route", { exact: true }).first().click();
  await page.getByRole("button", { name: "Open the whole route in Google Maps" }).waitFor();
  await snap("11-route", true);
  await page.goBack();
  await page.getByText(/Priority \d+/).first().waitFor();

  await page.getByRole("button", { name: /^Done \(/ }).click();
  await snap("03-jobs-done");
  await page.getByRole("button", { name: /^To do \(/ }).click();

  await page.getByText(/Priority \d+/).first().click();
  await page.getByText("Your steps").waitFor();
  await page.waitForTimeout(1800);
  await snap("04-job-detail", true);
  await page.goBack();

  await tab("Location");
  await page.getByText("Vehicle location").first().waitFor();
  await snap("05-location");
  const phoneTruck = page.getByRole("button", { name: "Crew phone truck" });
  if (await phoneTruck.count()) await phoneTruck.first().click();
  await page.getByRole("button", { name: "Start sharing" }).click();
  await page.getByText(/Last sent/).waitFor({ timeout: 20000 });
  await snap("06-location-sharing");
  await page.getByRole("button", { name: "Stop sharing" }).click();
  await page.waitForTimeout(500);

  await tab("Report");
  await page.getByText("Report a site").first().waitFor();
  await snap("07-report", true);
  await tab("Account");
  await page.getByText("Sign out").first().waitFor();
  await snap("08-account");
  return { problems, written };
}

const browser = await chromium.launch();
const results = {};
for (const [name, run] of [["resident", resident], ["crew", crew]]) {
  try {
    results[name] = await run(browser);
  } catch (error) {
    // keep a picture of where it stopped, to see why
    for (const ctx of browser.contexts()) for (const pg of ctx.pages()) await pg.screenshot({ path: path.join(OUT, name, "_stopped.png") }).catch(() => {});
    results[name] = { error: String(error.message).split("\n")[0] };
  }
}
await browser.close();
console.log(JSON.stringify(results, null, 1));
