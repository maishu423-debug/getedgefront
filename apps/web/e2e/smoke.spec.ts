import { expect, type Page, test } from "@playwright/test";

async function noHorizontalScroll(page: Page) {
  const { sw, cw } = await page.evaluate(() => ({
    sw: document.documentElement.scrollWidth,
    cw: document.documentElement.clientWidth,
  }));
  expect(sw, "page must not scroll horizontally").toBeLessThanOrEqual(cw);
}

test.describe("homepage", () => {
  test("board renders real rows, strip and feed", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      "Observed weather at the U.S. stations weather markets settle on.",
    );
    const board = page.getByRole("table", { name: /Settlement stations/ });
    await expect(board).toBeVisible();
    const rows = board.locator("tbody tr").filter({ has: page.locator('a[href^="/station/K"]') });
    expect(await rows.count()).toBeGreaterThanOrEqual(20);
    await expect(board.getByRole("link", { name: /KDFW/ }).first()).toBeVisible();
    await expect(page.getByLabel("Data status")).toContainText("METARs fetched");
    await expect(page.getByRole("heading", { name: "Recent new highs" })).toBeVisible();
    await expect(page.getByText("Design mockup")).toHaveCount(0);
    await noHorizontalScroll(page);
  });

  test("venue filter and sort update the URL", async ({ page }) => {
    await page.goto("/");
    const board = page.getByRole("table", { name: /Settlement stations/ });
    await expect(board.locator('a[href^="/station/K"]').first()).toBeVisible(); // board streamed in
    const all = await board.locator('a[href^="/station/K"]').count();
    await page
      .getByRole("group", { name: "Venue" })
      .getByRole("button", { name: "Polymarket" })
      .click();
    await expect(page).toHaveURL(/\?venue=polymarket/);
    await expect(page.getByRole("button", { name: "Polymarket" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    const poly = await board.locator('a[href^="/station/K"]').count();
    expect(poly).toBeLessThan(all);
    await page.getByRole("group", { name: "Sort" }).getByRole("button", { name: "A–Z" }).click();
    await expect(page).toHaveURL(/venue=polymarket&sort=az|sort=az&venue=polymarket/);
    await page.reload();
    await expect(page.getByRole("button", { name: "A–Z" })).toHaveAttribute("aria-pressed", "true");
  });

  test("search finds a station by alias and opens it", async ({ page }) => {
    await page.goto("/");
    const box = page.getByRole("combobox", { name: "Search stations" });
    await box.fill("vegas");
    await expect(page.getByRole("option", { name: /KLAS/ })).toBeVisible();
    await box.press("Enter");
    await expect(page).toHaveURL(/\/station\/KLAS$/);
    await page.goto("/");
    await page.getByRole("combobox", { name: "Search stations" }).fill("zzzzz");
    await expect(page.getByText(/No station matches/)).toBeVisible();
  });
});

test.describe("station pages", () => {
  test("KDFW shows every section", async ({ page }) => {
    await page.goto("/station/KDFW");
    await expect(page.getByRole("heading", { level: 1, name: "KDFW" })).toBeVisible();
    for (const name of [
      "Current temperature",
      "Today's high so far",
      "NWS forecast · Today",
      "Daily summaries",
      "Observed conditions",
      "Hourly METAR reports",
    ]) {
      await expect(page.getByRole("heading", { name })).toBeVisible();
    }
    await expect(page.getByText("FORECAST", { exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Full forecast on weather.gov" })).toHaveAttribute(
      "href",
      /forecast\.weather\.gov\/MapClick\.php\?lat=/,
    );
    // Chart: lazy-loaded canvas + accessible text summary.
    await expect(page.locator('[aria-label^="Observed conditions chart"] canvas')).toHaveCount(1);
    await expect(page.getByText(/reports .*in the last 24 h/)).toBeVisible();
    // Daily summaries: four product rows (or their status text).
    const daily = page.getByRole("table", { name: /Daily climate reports/ });
    await expect(daily.getByText("CLI").first()).toBeVisible();
    await expect(daily.getByText("DSM").first()).toBeVisible();
    // METAR list toggles to decoded and expands to 24 h.
    await page
      .getByRole("group", { name: "METAR view" })
      .getByRole("button", { name: "Decoded" })
      .click();
    await expect(page.getByRole("table", { name: /Decoded METAR reports/ })).toBeVisible();
    await noHorizontalScroll(page);
  });

  test("lower-case id redirects to the canonical upper-case URL", async ({ page }) => {
    const res = await page.goto("/station/kdfw");
    expect(res?.url()).toMatch(/\/station\/KDFW$/);
  });

  test("KBKF shows one clear 'no daily summary' message", async ({ page }) => {
    await page.goto("/station/KBKF");
    await expect(page.getByText("No daily summary available for this station")).toBeVisible();
    await expect(page.getByRole("table", { name: /Daily climate reports/ })).toHaveCount(0);
    await noHorizontalScroll(page);
  });

  test("unknown station and unknown page show the friendly 404", async ({ page }) => {
    await page.goto("/station/KZZZ");
    await expect(page.getByRole("heading", { name: "We couldn't find that page" })).toBeVisible();
    await expect(page.getByRole("combobox", { name: "Search stations" })).toBeVisible();
    const res = await page.goto("/no-such-page");
    expect(res?.status()).toBe(404);
  });
});

test.describe("other pages", () => {
  for (const [path, heading] of [
    ["/pricing", "Pricing"],
    ["/sources", "Sources and definitions"],
    ["/terms", "Terms and data licences"],
    ["/privacy", "Privacy"],
  ] as const) {
    test(`${path} renders`, async ({ page }) => {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
      await noHorizontalScroll(page);
    });
  }

  test("legal pages are marked as drafts; pricing has no prices or email form", async ({
    page,
  }) => {
    await page.goto("/terms");
    await expect(page.getByText("Draft — pending legal review")).toBeVisible();
    await page.goto("/pricing");
    await expect(page.getByRole("button", { name: "Coming soon" })).toBeDisabled();
    await expect(page.locator('input[type="email"]')).toHaveCount(0);
    await expect(page.getByText(/\$\d/)).toHaveCount(0);
  });

  test("sitemap lists every station", async ({ request }) => {
    const xml = await (await request.get("/sitemap.xml")).text();
    expect((xml.match(/\/station\/K[A-Z0-9]{3}/g) ?? []).length).toBeGreaterThanOrEqual(28);
  });
});
