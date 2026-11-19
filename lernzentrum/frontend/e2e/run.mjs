// End-to-end smoke test: drives every screen in iPad (landscape + portrait), desktop and iPhone viewports
// against a running stack (demo mode). Usage: BASE_URL=http://localhost:3000 node e2e/run.mjs [outDir]
import { mkdirSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
let playwright;
try {
  playwright = require("playwright");
} catch {
  playwright = require(require.resolve("playwright", { paths: ["/usr/lib/node_modules", "/usr/local/lib/node_modules"] }));
}
const { chromium, devices } = playwright;
const BASE = process.env.BASE_URL || "http://localhost:3000";
const OUT = process.argv[2] || "e2e-shots";
mkdirSync(OUT, { recursive: true });

const failures = [];
const check = (cond, msg) => {
  if (!cond) failures.push(msg);
  console.log(`${cond ? "✓" : "✗"} ${msg}`);
};

async function session(name, contextOpts, full) {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ ...contextOpts, locale: "de-DE", timezoneId: "Europe/Berlin", permissions: ["microphone"] });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => m.type() === "error" && !m.text().includes("401") && errors.push(`console: ${m.text()}`));
  page.on("response", (r) => {
    if (r.url().includes("/api/") && r.status() >= 500) errors.push(`HTTP ${r.status()} ${r.url()}`);
  });
  const shot = (n) => page.screenshot({ path: `${OUT}/${name}-${n}.png`, fullPage: false });

  await page.goto(`${BASE}/login`);
  await page.getByRole("button", { name: "Demo öffnen" }).click();
  await page.waitForURL(`${BASE}/`);
  await page.getByText("Fristen").first().waitFor();
  check(await page.getByText("Läuft jetzt").isVisible(), `${name}: home shows running lecture (one-tap start)`);
  await shot("home");

  if (full) {
    // live mode: consent → session → demo lecture
    await page.getByRole("button", { name: "Aufnahme starten" }).first().click();
    const startBtn = page.getByRole("dialog").getByRole("button", { name: "Aufnahme starten" });
    check(await startBtn.isDisabled(), `${name}: start disabled until consent`);
    await page.getByRole("dialog").getByRole("checkbox").check();
    await startBtn.click();
    await page.waitForURL(/\/live\/\d+/);
    await page.getByRole("button", { name: /Demo-Vorlesung abspielen/ }).click();
    await page.waitForSelector("article[aria-label^='Antwort']", { timeout: 45000 });
    check(true, `${name}: live answer card appeared`);
    await page.waitForTimeout(27000);
    const cards = await page.locator("article[aria-label^='Antwort']").count();
    check(cards >= 2, `${name}: ${cards} answer cards (incl. follow-up)`);
    check(await page.getByText(/Dozent sagt gerade/).count() > 0, `${name}: lecturer correction flagged`);
    check(await page.getByText("Normen im Wortlaut").isVisible(), `${name}: statute quotes shown`);
    check(await page.getByText("Zahlen & Fristen").isVisible(), `${name}: number keeper shown`);
    check(await page.getByText("Klausurhinweise").isVisible(), `${name}: keyword alert list shown`);
    await shot("live");
    await page.getByRole("button", { name: /Ausblenden/ }).click();
    check(await page.getByText(/Antworten ausgeblendet/).isVisible(), `${name}: one-tap hide works`);
    await shot("live-hidden");
    await page.getByRole("button", { name: "Einblenden", exact: true }).click();
    await page.getByRole("button", { name: "Ausführlich" }).click();
    const src = page.locator("article[aria-label^='Antwort'] button").filter({ hasText: /Folie|BGB|HGB|AO/ }).first();
    if (await src.count()) {
      await src.click();
      check(await page.getByRole("dialog").isVisible(), `${name}: source sheet opens`);
      await shot("source");
      await page.getByRole("button", { name: "Schließen" }).click();
    }
    await page.getByRole("button", { name: /Beenden/ }).click();
    await page.waitForTimeout(3000);
  }

  const pages = [
    ["modules", "/modules", "Jedes Modul hat"],
    ["module", "/modules/1", "Übersicht"],
    ["module-cards", "/modules/1?tab=cards", "Frage"],
    ["module-radar", "/modules/2?tab=radar", "Klausur-Radar"],
    ["module-mock", "/modules/1?tab=mock", "Probeklausur starten"],
    ["learn", "/learn?tab=ask", "Frag dein Material"],
    ["learn-case", "/learn?tab=case", "Fall im Gutachtenstil"],
    ["learn-stats", "/learn?tab=stats", "Lernzeit pro Modul"],
    ["learn-history", "/learn?tab=history", "Antwortverlauf"],
    ["library", "/library", "Dokumente"],
    ["inbox", "/inbox?tab=review", "Termine ohne Modul"],
    ["calendar", "/calendar", "Fristen"],
    ["settings", "/settings", "Verbindungen"],
  ];
  for (const [n, path, text] of pages) {
    await page.goto(`${BASE}${path}`);
    try {
      await page.getByText(text).first().waitFor({ timeout: 15000 });
      check(true, `${name}: ${path} renders`);
    } catch {
      check(false, `${name}: ${path} renders (missing "${text}")`);
    }
    if (full || ["module", "settings", "inbox"].includes(n)) await shot(n);
  }

  if (full) {
    await page.goto(`${BASE}/library`);
    await page.getByLabel("Suche").fill("Verjährungsfrist drei Jahre");
    await page.getByRole("button", { name: "Suchen" }).click();
    await page.getByText(/Treffer/).waitFor();
    check(await page.getByText(/Folie 5/).count() > 0, `${name}: search finds slide with page location`);
    await shot("search");
    await page.goto(`${BASE}/learn?tab=ask`);
    await page.getByPlaceholder(/Was hat der Dozent/).fill("Wie lange müssen Buchungsbelege aufbewahrt werden?");
    await page.getByRole("button", { name: "Fragen" }).click();
    await page.waitForSelector("article[aria-label^='Antwort']");
    await shot("ask");
    await page.goto(`${BASE}/modules/1?tab=mock`);
    await page.getByRole("button", { name: /Probeklausur starten/ }).click();
    await page.getByRole("button", { name: "Abgeben" }).click();
    await page.getByText(/Note \d/).first().waitFor();
    check(true, `${name}: mock exam graded`);
  }
  check(errors.length === 0, `${name}: no runtime errors${errors.length ? ` (${errors.slice(0, 5).join(" | ")})` : ""}`);
  await browser.close();
}

await session("ipad-landscape", { viewport: { width: 1194, height: 834 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true, userAgent: devices["iPad Pro 11"].userAgent }, true);
await session("ipad-portrait", { viewport: { width: 834, height: 1194 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true, userAgent: devices["iPad Pro 11"].userAgent }, false);
await session("desktop", { viewport: { width: 1440, height: 900 } }, false);
await session("iphone", { ...devices["iPhone 14"], deviceScaleFactor: 1 }, false);

console.log(failures.length ? `\n${failures.length} FAILURE(S)` : "\nALL CHECKS PASSED");
process.exit(failures.length ? 1 : 0);
