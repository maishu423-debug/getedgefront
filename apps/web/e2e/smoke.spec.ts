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
      "Model guidance for Dallas/Fort Worth Intl",
    ]) {
      await expect(page.getByRole("heading", { name })).toBeVisible();
    }
    await expect(page.getByText("FORECAST", { exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Full forecast on weather.gov" })).toHaveAttribute(
      "href",
      /forecast\.weather\.gov\/MapClick\.php\?lat=/,
    );
    // Chart: loaded only when scrolled near (Phase 6 B1) + accessible text summary.
    const obsChart = page.locator('[aria-label^="Observed conditions chart"]');
    await obsChart.scrollIntoViewIfNeeded();
    await expect(obsChart.locator("canvas")).toHaveCount(1);
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
    const st = await page.goto("/station/KZZZ");
    expect(st?.status(), "unknown station must be a real 404").toBe(404);
    await expect(page.getByRole("heading", { name: "We couldn't find that page" })).toBeVisible();
    await expect(page.getByRole("combobox", { name: "Search stations" })).toBeVisible();
    const res = await page.goto("/no-such-page");
    expect(res?.status()).toBe(404);
  });
});

test.describe("model guidance", () => {
  const section = (page: Page) =>
    page.locator("section", { has: page.getByRole("heading", { name: /^Model guidance for / }) });

  test("KDFW shows at least 6 models, a lazy chart and run lines", async ({ page }) => {
    await page.goto("/station/KDFW");
    const s = section(page);
    await s.scrollIntoViewIfNeeded();
    await expect(s.getByText("MODEL DATA", { exact: true })).toBeVisible();
    const chart = s.locator('[aria-label^="Model guidance chart"]');
    await chart.scrollIntoViewIfNeeded(); // ECharts loads only near the viewport
    await expect(chart.locator("canvas")).toHaveCount(1);
    const on = s.locator('button[aria-pressed="true"]').filter({ hasNotText: /^(Temp|Today)$/ });
    // chips that are available and switched on (variable/span tabs excluded by name)
    const chips = s.locator('[role="group"][aria-label$=" models"] button[aria-pressed]');
    expect(await chips.count()).toBeGreaterThanOrEqual(6);
    expect(await on.count()).toBeGreaterThanOrEqual(6);
    await expect(s.getByRole("list", { name: "Model runs shown" })).toContainText("run ");
    await expect(s.getByText(/© ECMWF, open data licensed under CC BY 4\.0/)).toBeVisible();
    await noHorizontalScroll(page);
  });

  test("KMIA: PFM chip is disabled and explains why", async ({ page }) => {
    await page.goto("/station/KMIA");
    const s = section(page);
    const pfm = s.getByRole("button", { name: /PFM/ });
    await expect(pfm).toHaveAttribute("aria-disabled", "true");
    await pfm.focus();
    await expect(s.getByRole("tooltip")).toContainText("no PFM point");
    await expect(s.getByRole("list", { name: "Model runs shown" })).toContainText(
      "Not available for this station",
    );
  });

  test("variable, window and chips are kept in the URL", async ({ page }) => {
    await page.goto("/station/KDFW");
    const s = section(page);
    await s.getByRole("group", { name: "Variable" }).getByRole("button", { name: "Wind" }).click();
    await expect(page).toHaveURL(/mvar=wind/);
    await s
      .getByRole("group", { name: "Forecast window" })
      .getByRole("button", { name: "48 h" })
      .click();
    await expect(page).toHaveURL(/mspan=48h/);
    await s.getByRole("button", { name: /^NBM/ }).click();
    await expect(page).toHaveURL(/mhide=nbm/);
    await page.reload();
    const s2 = section(page);
    await expect(s2.getByRole("button", { name: "Wind" })).toHaveAttribute("aria-pressed", "true");
    await expect(s2.getByRole("button", { name: "48 h" })).toHaveAttribute("aria-pressed", "true");
    await expect(s2.getByRole("button", { name: /^NBM/ })).toHaveAttribute("aria-pressed", "false");
    await expect(s2.getByText(/Model wind speed for 48 h/)).toBeVisible();
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

  test("legal pages are marked as drafts; pricing has no email form", async ({ page }) => {
    await page.goto("/terms");
    await expect(page.getByText("Draft — pending legal review")).toBeVisible();
    await page.goto("/pricing");
    // v2: signed out, the CTA leads to sign-in, then back here (checkout: billing.spec.ts).
    // The price itself comes from Stripe (v2 Phase 8), so it is no longer absent.
    await expect(page.getByRole("link", { name: "Start 7-day free trial" })).toHaveAttribute(
      "href",
      "/signin?next=%2Fpricing",
    );
    await expect(page.locator('input[type="email"]')).toHaveCount(0);
  });

  test("sitemap lists every station", async ({ request }) => {
    const xml = await (await request.get("/sitemap.xml")).text();
    expect((xml.match(/\/station\/K[A-Z0-9]{3}/g) ?? []).length).toBeGreaterThanOrEqual(28);
  });
});

test.describe("deployment guards", () => {
  test("no CSP violations on any page type (charts included)", async ({ page }) => {
    const violations: string[] = [];
    page.on("console", (m) => {
      if (/Content.Security.Policy|Refused to/i.test(m.text())) violations.push(m.text());
    });
    for (const path of ["/", "/station/KDFW?mvar=cloud&mspan=48h", "/sources", "/pricing"]) {
      await page.goto(path);
      for (const name of ["Observed conditions chart", "Model guidance chart"]) {
        const chart = page.locator(`[aria-label^="${name}"]`);
        if (await chart.count()) {
          await chart.scrollIntoViewIfNeeded();
          await expect(chart.locator("canvas")).toHaveCount(1);
          await chart.hover();
        }
      }
    }
    expect(violations).toEqual([]);
  });

  test("security headers, noindex and robots.txt before go-live", async ({ request }) => {
    const res = await request.get("/");
    const h = res.headers();
    expect(h["x-content-type-options"]).toBe("nosniff");
    expect(h["referrer-policy"]).toBe("strict-origin-when-cross-origin");
    expect(h["x-robots-tag"]).toBe("noindex, nofollow");
    const csp = h["content-security-policy"] ?? h["content-security-policy-report-only"];
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).not.toContain("unsafe-eval");
    const robots = await (await request.get("/robots.txt")).text();
    expect(robots).toMatch(/Disallow: \/\s*$/m);
  });

  test("/api/health reports api, db and source health", async ({ request }) => {
    const res = await request.get("/api/health");
    expect([200, 503]).toContain(res.status());
    const body = await res.json();
    expect(["ok", "degraded", "down"]).toContain(body.status);
    expect(res.headers()["x-robots-tag"]).toBe("noindex, nofollow");
  });
});
