import { expect, test } from "@playwright/test";

test("every view loads under the production CSP without errors", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "What to build next, and the evidence for it" })).toBeVisible();
  await expect(page.locator(".forest svg")).toBeVisible();
  for (const [tab, heading] of [["Bets", "The bets"], ["Blind check", "The blind check"], ["Glossary review", "Glossary review"]] as const) {
    await page.getByRole("tab", { name: tab }).click();
    await expect(page.getByRole("heading", { name: heading, level: 1 })).toBeVisible();
  }
  expect(errors).toEqual([]);
});

test("glossary: approve one proposal and it leaves the queue", async ({ page }) => {
  await page.goto("/#glossary");
  const first = page.locator(".queue__item").first();
  const word = await first.locator(".queue__word").innerText();
  await first.getByRole("button", { name: /^Approve/ }).click();
  await expect(page.locator(".queue__word", { hasText: new RegExp(`^${word}$`) })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Download decisions" })).toBeEnabled();
});

test("a missing data file shows an error with a retry", async ({ page }) => {
  await page.route("**/data/bets.json", (r) => r.fulfill({ status: 404, body: "" }));
  await page.goto("/#bets");
  await expect(page.getByRole("alert")).toContainText("dgp export-web");
});
