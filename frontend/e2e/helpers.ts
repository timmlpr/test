import { expect, type Page } from "@playwright/test";

export async function loginDemo(page: Page, email = "demo@demo.example.com") {
  await page.goto("/login");
  await page.getByLabel("E-Mail-Adresse").fill(email);
  await page.getByLabel("Passwort", { exact: true }).fill("FadeprintDemo1!");
  await page.getByRole("button", { name: "Anmelden", exact: true }).click();
  await expect(page).toHaveURL(/\/app$/);
  await page.evaluate(() => localStorage.setItem("fp_cookie", "necessary"));
}

export function trackErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error" && !/401|402|Failed to load resource/.test(m.text())) errors.push(`console: ${m.text()}`); });
  return errors;
}
