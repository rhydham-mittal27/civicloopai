import { chromium } from "@playwright/test";

const out = process.argv[2];
const photo = process.argv[3];
const browser = await chromium.launch();

async function open(viewport, name) {
  const ctx = await browser.newContext({ viewport, permissions: ["geolocation"], geolocation: { latitude: 30.7398, longitude: 76.7827, accuracy: 18 } });
  const page = await ctx.newPage();
  const problems = [];
  page.on("pageerror", (e) => problems.push(String(e)));
  await page.goto("http://localhost:3000/login");
  await page.getByLabel("Email").fill("resident@civic.test");
  await page.getByLabel("Password").fill("resident-pass-1234");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL(/incidents$/);
  await page.goto("http://localhost:3000/incidents/new");
  await page.getByRole("heading", { name: "Report an incident" }).waitFor();
  await page.waitForTimeout(1800);
  await page.screenshot({ path: `${out}/${name}-blank.png`, fullPage: viewport.width < 600 });
  return { page, ctx, problems };
}

// desktop: the full journey
{
  const { page, ctx, problems } = await open({ width: 1440, height: 900 }, "report-desktop");
  await page.getByRole("button", { name: "Submit report" }).click();
  await page.getByText("Tell us what you saw").waitFor();
  console.log("empty submit shows:", (await page.locator(".field-error").allInnerTexts()).join(" | "));

  await page.getByRole("button", { name: "Blocked drain" }).click();
  await page.getByRole("button", { name: "Plastic litter" }).click();
  console.log("description:", await page.getByLabel("What did you see?").inputValue());

  // tap the map to drop a pin
  const box = await page.locator(".picker svg").boundingBox();
  await page.mouse.click(box.x + box.width * 0.55, box.y + box.height * 0.45);
  await page.waitForTimeout(500);
  console.log("pin placed:", await page.locator(".dropped").count(), "| coords:", await page.locator("#lat").inputValue(), await page.locator("#lon").inputValue());

  await page.locator("#photo-input").setInputFiles([photo, photo]);
  await page.getByAltText("Attached photo 2").waitFor();
  console.log("photos:", await page.locator(".shot").count(), "| checklist done:", await page.locator(".checklist li[data-done]").count());
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${out}/report-desktop-filled.png`, fullPage: true });

  await page.getByRole("button", { name: "Use my location" }).click();
  await page.waitForTimeout(900);
  console.log("after GPS:", await page.locator(".field-foot").nth(1).innerText());

  await page.getByRole("button", { name: "Submit report" }).click();
  await page.waitForURL(/incidents\/[0-9a-f-]{36}/, { timeout: 20000 });
  await page.locator('img[alt="Before cleanup"]').first().waitFor();
  console.log("submitted; detail photos:", await page.locator('img[alt="Before cleanup"]').count());
  console.log("draft cleared:", await page.evaluate(() => localStorage.getItem("civicloop.report-draft")));
  console.log("problems:", problems.length ? problems : "none");
  await ctx.close();
}

// phone
{
  const { page, ctx } = await open({ width: 390, height: 844 }, "report-phone");
  const wide = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  console.log("phone overflow px:", wide);
  await ctx.close();
}
await browser.close();
