import { expect, test } from "@playwright/test";
import { loginDemo } from "./helpers";

for (const p of ["/", "/preise", "/app", "/app/results", "/app/requests", "/app/scam", "/app/graph", "/app/risk", "/app/settings"]) {
  test(`mobile layout has no horizontal scroll: ${p}`, async ({ page }) => {
    if (p.startsWith("/app")) await loginDemo(page);
    await page.goto(p);
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });
}

test("mobile bottom navigation", async ({ page }) => {
  await loginDemo(page);
  await expect(page.getByRole("navigation", { name: "Schnellnavigation" })).toBeVisible();
  await page.getByRole("navigation", { name: "Schnellnavigation" }).getByText("Mehr").click();
  await expect(page.getByRole("dialog", { name: "Menü" })).toBeVisible();
});
