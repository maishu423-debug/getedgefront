import { expect, test } from "@playwright/test";

// Phase 0 placeholder. Phase 4 replaces this with: home renders the board with real rows,
// and a station page renders all sections. Run against a running stack: `pnpm test:e2e`.
test("home page renders", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("EdgeFront");
});
