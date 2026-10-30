import { expect, test } from "@playwright/test";

test("phone: no sideways scroll; the roadmap stacks", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "What to build next, and the evidence for it" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
