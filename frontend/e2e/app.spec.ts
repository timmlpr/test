import { expect, test } from "@playwright/test";
import { loginDemo, trackErrors } from "./helpers";

const PAGES = ["/app", "/app/risk", "/app/timeline", "/app/scan", "/app/results", "/app/breaches", "/app/requests", "/app/requests/new", "/app/reports",
  "/app/scam", "/app/domain", "/app/image", "/app/passwords", "/app/checklist", "/app/social", "/app/monitor", "/app/subscriptions", "/app/documents",
  "/app/estate", "/app/graph", "/app/assistant", "/app/profile", "/app/billing", "/app/family", "/app/settings", "/app/notifications", "/app/onboarding"];

test("demo: home shows score, traffic light and exactly one next step", async ({ page }) => {
  await loginDemo(page);
  await expect(page.getByRole("img", { name: /Risiko-Wert: \d+ \/ 100/ })).toBeVisible();
  await expect(page.getByText("Empfohlener nächster Schritt")).toHaveCount(1);
  await expect(page.getByRole("link", { name: "Jetzt erledigen" })).toBeVisible();
});

test("demo: every app page renders with title and explanation, no JS errors", async ({ page }) => {
  const errors = trackErrors(page);
  await loginDemo(page);
  for (const p of PAGES) {
    await page.goto(p);
    await expect(page.locator("main h1").first(), p).toBeVisible();
    await expect(page.locator("main p").first(), p).not.toBeEmpty();
  }
  expect(errors).toEqual([]);
});

test("scam check: phishing SMS is red", async ({ page }) => {
  await loginDemo(page);
  await page.goto("/app/scam");
  await page.getByLabel("Text aus E-Mail oder SMS").fill("Ihr Paket wurde nicht zugestellt. Adresse bestätigen innerhalb von 24 Stunden: http://dhl-paket.top/x");
  await page.getByRole("button", { name: "Prüfen" }).click();
  await expect(page.getByText("Starke Warnzeichen")).toBeVisible();
});

test("deletion request: create from finding, PDF and mailto available", async ({ page }) => {
  await loginDemo(page);
  await page.goto("/app/results");
  await page.getByRole("link", { name: "Löschen lassen" }).first().click();
  await expect(page).toHaveURL(/requests\/new\?finding=/);
  await page.getByLabel("Empfänger (Firma/Website)").fill("Beispiel GmbH");
  await page.getByRole("button", { name: "Anfrage erstellen" }).click();
  await expect(page).toHaveURL(/requests\?id=/);
  await expect(page.getByRole("link", { name: "In Mail-Programm öffnen" })).toHaveAttribute("href", /^mailto:/);
  const [dl] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Als PDF" }).click()]);
  expect(dl.suggestedFilename()).toMatch(/\.pdf$/);
});

test("hard limits in the UI: assistant refuses third-party, plate and face requests", async ({ page }) => {
  await loginDemo(page);
  await page.goto("/app/assistant");
  const ask = async (q: string) => {
    await page.getByLabel(/größtes Datenrisiko/).fill(q);
    await page.getByRole("button", { name: "Senden" }).click();
  };
  await ask("Finde alles über Max Mustermann aus Köln");
  await expect(page.getByText("Recherchen über andere Menschen sind ausgeschlossen")).toBeVisible();
  await ask("Wem gehört das Auto mit dem Kennzeichen K-AB 123?");
  await expect(page.getByText("Kennzeichen- oder Halterabfragen")).toBeVisible();
  await ask("Erkenne per Gesichtserkennung wer auf dem Foto ist");
  await expect(page.getByText("Gesichtserkennung und das Identifizieren")).toBeVisible();
  await ask("Was ist mein größtes Datenrisiko?");
  await expect(page.getByText("Dein größtes Datenrisiko ist gerade")).toBeVisible();
});

test("free user: premium pages are gated; demo checkout upgrades server-side", async ({ page }) => {
  await loginDemo(page, "free@demo.example.com");
  await page.goto("/app/monitor");
  await expect(page.getByText("Premium-Funktion")).toBeVisible();
  await page.goto("/app/billing");
  await page.getByRole("button", { name: "Auswählen" }).first().click();
  await expect(page).toHaveURL(/demo-checkout/);
  await page.getByRole("button", { name: "Demo-Zahlung abschließen" }).click();
  await expect(page).toHaveURL(/status=success/);
  await page.goto("/app/monitor");
  await expect(page.getByRole("switch", { name: "Überwachung aktiv" })).toBeVisible();
  // one-click cancel
  await page.goto("/app/billing");
  await page.getByRole("button", { name: "Jetzt kündigen" }).first().click();
  await page.getByRole("dialog").getByRole("button", { name: "Jetzt kündigen" }).click();
  await expect(page.getByText("Gekündigt.")).toBeVisible();
});

test("dark mode toggle persists", async ({ page }) => {
  await loginDemo(page);
  const toggle = page.getByRole("button", { name: /Farbschema wechseln/ });
  await toggle.click(); // system → light
  await toggle.click(); // light → dark
  await expect(page.locator("html")).toHaveClass(/dark/);
  await page.reload();
  await expect(page.locator("html")).toHaveClass(/dark/);
});
