import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { expect, type Page } from "@playwright/test";

/** Logs in once per account and reuses the session cookies afterwards (keeps us under the real login rate limit). */
export async function loginDemo(page: Page, email = "demo@demo.example.com") {
  const file = `test-results/.auth-${email}.json`;
  if (existsSync(file)) {
    await page.context().addCookies(JSON.parse(readFileSync(file, "utf8")));
    await page.goto("/app");
    if (/\/app$/.test(page.url())) { await page.evaluate(() => localStorage.setItem("fp_cookie", "necessary")); return; }
  }
  await page.goto("/login");
  await page.getByLabel("E-Mail-Adresse").fill(email);
  await page.getByLabel("Passwort", { exact: true }).fill("TracelowDemo1!");
  await page.getByRole("button", { name: "Anmelden", exact: true }).click();
  await expect(page).toHaveURL(/\/app$/);
  await page.evaluate(() => localStorage.setItem("fp_cookie", "necessary"));
  mkdirSync("test-results", { recursive: true });
  writeFileSync(file, JSON.stringify(await page.context().cookies()));
}

export function trackErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error" && !/401|402|Failed to load resource/.test(m.text())) errors.push(`console: ${m.text()}`); });
  return errors;
}
