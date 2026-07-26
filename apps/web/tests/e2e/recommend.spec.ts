import { expect, test } from "@playwright/test";

// Gated e2e: requires a fully running stack (web + api + db + Clerk test user).
// Run with `pnpm test:e2e`, NOT part of `pnpm test` or `make check` — CI without
// a live backend would fail otherwise. This file documents the happy path; the
// test-user auth setup is an operational concern (Clerk testing tokens).

test.describe("recommendation flow", () => {
  test.skip(
    !process.env.E2E_BASE_URL,
    "set E2E_BASE_URL + a signed-in storage state to run",
  );

  test("sign-in → query → streamed picks → feedback", async ({ page }) => {
    await page.goto(process.env.E2E_BASE_URL!);
    // Assumes storageState carries a Clerk session (configured in playwright.config).
    await page.getByPlaceholder(/e\.g\./).fill("psychological thriller under 24 episodes");
    await page.getByRole("button", { name: /get recommendations/i }).click();

    // Three recommendation cards render.
    await expect(page.getByRole("heading", { level: 3 })).toHaveCount(0); // titles are links, not headings
    await expect(page.locator("text=Why this matches:")).toHaveCount(3);

    // Thumbs up the first pick.
    await page.getByLabel("thumbs up").first().click();
  });
});
