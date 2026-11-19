import { expect, test } from "@playwright/test";
import { trackErrors } from "./helpers";

test("landing page: hero, steps, pricing, FAQ, trust, waitlist", async ({ page }) => {
  const errors = trackErrors(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("digitalen Fußabdruck");
  await expect(page.getByRole("heading", { name: "So funktioniert’s" })).toBeVisible();
  await expect(page.getByText("3,99 €").first()).toBeVisible();
  await expect(page.getByText("Am beliebtesten")).toHaveCount(0); // not claimed without data
  await page.getByText("Sucht Tracelow auch nach anderen Personen?").click();
  await expect(page.getByText("ausschließlich nach deinen eigenen")).toBeVisible();
  await page.locator("#wl-email").fill(`e2e-${Date.now()}@example.org`);
  await page.getByText("Ich möchte per E-Mail über den Start").click();
  await page.getByRole("button", { name: "Eintragen" }).click();
  await expect(page.getByText("Fast geschafft")).toBeVisible();
  expect(errors).toEqual([]);
});

test("public pages render", async ({ page }) => {
  for (const [path, text] of [["/preise", "Preise"], ["/blog", "Ratgeber"], ["/blog/loeschanfrage-dsgvo-art-17", "Art. 17"],
    ["/rechtliches/impressum", "Impressum"], ["/rechtliches/datenschutz", "Datenschutzerklärung"], ["/rechtliches/agb", "Geschäftsbedingungen"],
    ["/rechtliches/widerruf", "Widerrufsbelehrung"], ["/rechtliches/nutzungsbedingungen", "Missbrauchsverbot"], ["/kuendigen", "Vertrag kündigen"],
    ["/missbrauch-melden", "Missbrauch melden"]] as const) {
    await page.goto(path);
    await expect(page.locator("main")).toContainText(text);
  }
  const sm = await page.request.get("/sitemap.xml");
  expect(await sm.text()).toContain("/blog/");
  const mf = await page.request.get("/manifest.webmanifest");
  expect((await mf.json()).icons.length).toBeGreaterThan(1);
});

test("cancellation button works without login (two steps)", async ({ page }) => {
  await page.goto("/kuendigen");
  await page.getByLabel("Name").fill("Test Person");
  await page.getByLabel("E-Mail-Adresse").fill("niemand@example.org");
  await page.getByRole("button", { name: "Weiter zur Bestätigung" }).click();
  await page.getByRole("button", { name: "Jetzt kündigen" }).click();
  await expect(page.getByText("Deine Kündigung ist eingegangen")).toBeVisible();
});

test("register → onboarding", async ({ page }) => {
  await page.goto("/register");
  await page.getByLabel("E-Mail-Adresse").fill(`neu-${Date.now()}@example.org`);
  await page.getByLabel("Passwort", { exact: true }).fill("ein-langes-passwort-123");
  await page.getByText("Ich akzeptiere die Nutzungsbedingungen").click();
  await page.getByRole("button", { name: "Konto erstellen" }).click();
  await expect(page).toHaveURL(/onboarding/);
  await expect(page.getByRole("heading", { name: /drei Schritten/ })).toBeVisible();
});
