import { expect, test } from "@playwright/test";

import { userIn } from "./premium-helpers";

// v2 Part 2: the legal pages, the footer links and the automatic-renewal disclosures.
const PAGES = [
  ["/terms", "Terms of Service"],
  ["/privacy", "Privacy Policy"],
  ["/refund", "Refund & Cancellation Policy"],
] as const;

test.describe("legal pages", () => {
  for (const [path, title] of PAGES) {
    test(`${path}: title, effective date at the top, headings as anchors`, async ({ page }) => {
      const res = await page.goto(path);
      expect(res?.status()).toBe(200);
      await expect(page.getByRole("heading", { level: 1 })).toHaveText(title);
      const eff = page.getByTestId("effective-date");
      await expect(eff).toContainText("Effective date:");
      // right under the title, before the contents list and the text
      const top = (l: import("@playwright/test").Locator) =>
        l.evaluate((e) => e.getBoundingClientRect().top);
      const [hY, eY, nY] = await Promise.all([
        top(page.getByRole("heading", { level: 1 })),
        top(eff),
        top(page.locator("article.legal")),
      ]);
      expect(hY).toBeLessThan(eY);
      expect(eY).toBeLessThan(nY);
      const ids = await page
        .locator("article.legal h2[id]")
        .evaluateAll((els) => els.map((e) => e.id));
      expect(ids.length).toBeGreaterThanOrEqual(path === "/refund" ? 6 : 10);
      const target = ids[2]!;
      await page
        .getByRole("navigation", { name: "On this page" })
        .locator(`a[href="#${target}"]`)
        .click();
      await expect(page).toHaveURL(new RegExp(`#${target}$`));
      await expect(page.locator(`[id="${target}"]`)).toBeInViewport();
    });
  }

  test("every page links all three policies in the footer (incl. the homepage)", async ({ page }) => {
    for (const path of ["/", "/station/KDFW", "/pricing", "/sources", "/map", "/signin", "/terms"]) {
      await page.goto(path);
      const footer = page.locator("footer");
      await expect(footer.getByRole("link", { name: "Terms of Service" })).toHaveAttribute("href", "/terms");
      await expect(footer.getByRole("link", { name: "Privacy Policy" })).toHaveAttribute("href", "/privacy");
      await expect(footer.getByRole("link", { name: "Refund & Cancellation Policy" })).toHaveAttribute("href", "/refund");
    }
  }); // prettier-ignore

  test("the privacy policy needs no sign-in", async ({ request }) => {
    const res = await request.get("/privacy", { maxRedirects: 0 });
    expect(res.status()).toBe(200);
    expect(await res.text()).toContain("Google user data");
  });
});

test.describe("renewal disclosures", () => {
  /** today + 7 days in the browser's time zone, as the page computes it */
  const expectedDate = (page: import("@playwright/test").Page) =>
    page.evaluate(() =>
      new Intl.DateTimeFormat("en-US", { month: "long", day: "numeric", year: "numeric" }).format(
        new Date(Date.now() + 7 * 86_400_000),
      ),
    );

  test("pricing, signed out in Stripe test mode: no checkout, so no button and no terms yet", async ({ page }) => {
    await page.goto("/pricing");
    await expect(page.getByText("Premium is coming soon")).toBeVisible();
    await expect(page.getByTestId("renewal-disclosure")).toHaveCount(0);
  }); // prettier-ignore

  test("signed in, trial available: pricing and account show the terms before checkout", async ({ page }, info) => {
    test.skip(!process.env.E2E_EMAIL_OUTBOX || !process.env.DATABASE_URL, "needs the e2e stack");
    await userIn(page, info, "free");
    const date = await expectedDate(page);
    await page.goto("/pricing");
    await expect(page.getByRole("button", { name: "Start 7-day free trial" })).toBeVisible();
    await expect(page.getByTestId("renewal-disclosure")).toHaveText(
      `7-day free trial, then $20/month plus applicable tax, renewing automatically each month until you cancel. Your card is charged on ${date} unless you cancel before then. Cancel anytime in Account → Manage billing.`,
    );
    const agree = page.getByTestId("agree-line");
    await expect(agree).toHaveText("By starting your trial you agree to the Terms and the Refund & Cancellation Policy.");
    await expect(agree.getByRole("link", { name: "Terms" })).toHaveAttribute("href", "/terms");
    await expect(agree.getByRole("link", { name: "Refund & Cancellation Policy" })).toHaveAttribute("href", "/refund");
    await page.goto("/account");
    await expect(page.getByTestId("renewal-disclosure")).toContainText("$20/month plus applicable tax");
    await expect(page.getByTestId("agree-line")).toBeVisible();
  }); // prettier-ignore

  test("sign-up: agree to the Terms, acknowledge the Privacy Policy (links, no pre-ticked box)", async ({ page }) => {
    await page.goto("/signin?mode=signup");
    const line = page.getByText(/By creating an account you agree to the Terms and acknowledge the Privacy Policy/);
    await expect(line).toBeVisible();
    await expect(line.getByRole("link", { name: "Terms" })).toHaveAttribute("href", "/terms");
    await expect(line.getByRole("link", { name: "Privacy Policy" })).toHaveAttribute("href", "/privacy");
    await expect(page.locator('input[type="checkbox"]:checked')).toHaveCount(0);
  }); // prettier-ignore
});
