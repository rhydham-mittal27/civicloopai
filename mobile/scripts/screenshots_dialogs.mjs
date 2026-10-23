// Captures the app's own dialogs, explainers, not-found screen and pull-to-refresh indicator.
//   node mobile/scripts/screenshots_dialogs.mjs <output-dir>
// Same setup as screenshots.mjs (backend :8000, previews :8082 resident and :8083 crew).
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const { chromium } = createRequire(path.resolve(here, "../../frontend/package.json"))("@playwright/test");
const OUT = path.resolve(process.argv[2] ?? "../docs/mobile");
const PHONE = { width: 390, height: 844 };

async function open(browser, base, name) {
  // no location permission granted, so the app's own "why we need it" dialog appears first
  const context = await browser.newContext({ viewport: PHONE, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  const page = await context.newPage();
  fs.mkdirSync(path.join(OUT, name), { recursive: true });
  const written = [];
  const snap = async (file) => {
    await page.waitForTimeout(700);
    await page.screenshot({ path: path.join(OUT, name, `${file}.png`) });
    written.push(`${name}/${file}.png`);
  };
  const tab = async (label) => {
    await page.getByText(label, { exact: true }).last().click();
    await page.waitForTimeout(600);
  };
  const signIn = async (email, password) => {
    await page.goto(base);
    await page.getByRole("button", { name: "Skip the introduction" }).click();
    await page.getByRole("button", { name: "Sign in" }).waitFor();
    await page.getByLabel("Email").locator("visible=true").first().fill(email);
    await page.getByLabel("Password").locator("visible=true").first().fill(password);
    await page.getByRole("button", { name: "Sign in" }).click();
  };
  return { page, snap, tab, signIn, written };
}

async function resident(browser) {
  const { page, snap, tab, signIn, written } = await open(browser, "http://localhost:8082", "resident");
  await signIn("resident@civic.test", "resident-pass-1234");
  await page.getByText("My reports").first().waitFor();
  await page.waitForTimeout(2500);

  // pull down at the top: the app's own refresh indicator
  const touch = await page.context().newCDPSession(page);
  const at = (y) => [{ x: 195, y }];
  await touch.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: at(200) });
  for (let i = 1; i <= 10; i++) await touch.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: at(200 + i * 14) });
  await page.waitForTimeout(300);
  await snap("12-pull-to-refresh");
  await touch.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await page.waitForTimeout(1800);

  await tab("Account");
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.getByText("Sign out?").waitFor();
  await snap("09-sign-out-dialog");
  await page.getByRole("button", { name: "Stay signed in" }).click();
  await page.waitForTimeout(500);

  await tab("Report");
  await page.getByRole("button", { name: "Use my location" }).click();
  await page.getByText("Use your location?").waitFor();
  await snap("10-location-explainer");
  await page.getByRole("button", { name: "Not now" }).click();
  await page.waitForTimeout(400);
  await page.goto("http://localhost:8082/nothing-here");
  await page.getByText("That page is not here").waitFor();
  await snap("13-not-found");
  return written;
}

async function crew(browser) {
  const { page, snap, tab, signIn, written } = await open(browser, "http://localhost:8083", "crew");
  await signIn("worker@civic.test", "worker-pass-123456");
  await page.getByText(/Priority \d+/).first().waitFor();
  await page.getByText("In progress", { exact: true }).first().click();
  await page.getByText("Your steps").waitFor();
  await page.getByRole("button", { name: "Mark as done" }).click();
  await page.getByText("Mark this cleanup as done?").waitFor();
  await snap("09-confirm-done-dialog");
  await page.getByRole("button", { name: "Not yet" }).click();
  await page.goBack();

  await tab("Location");
  await page.getByRole("button", { name: "Start sharing" }).click();
  await page.getByText("Share your vehicle's location?").waitFor();
  await snap("10-share-explainer");
  await page.getByRole("button", { name: "Not now" }).click();
  return written;
}

const browser = await chromium.launch();
const results = {};
for (const [name, run] of [["resident", resident], ["crew", crew]]) {
  try {
    results[name] = await run(browser);
  } catch (error) {
    for (const ctx of browser.contexts()) for (const pg of ctx.pages()) await pg.screenshot({ path: path.join(OUT, name, "_stopped.png") }).catch(() => {});
    results[name] = { error: String(error.message).split("\n")[0] };
  }
}
await browser.close();
console.log(JSON.stringify(results, null, 1));
