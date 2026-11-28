import AxeBuilder from "@axe-core/playwright";
import { expect, type APIRequestContext, type Page, test } from "@playwright/test";

import {
  blockOpenFreeMap,
  isPhone,
  recordRequests,
  setBilling,
  userIn,
  type BillingCase,
} from "./premium-helpers";

// v2 Phase 10: Premium UI, gating, leak tests and the live map. Needs the web server and API on a
// database seeded with `python -m edgefront_core.e2e_seed` (5-minute data with a stale station,
// a QC spike and two stations outside the feed) and DATABASE_URL pointing at it, plus the email
// outbox for sign-up. OpenFreeMap is blocked in every test: the map must work without it.
test.skip(!process.env.E2E_EMAIL_OUTBOX || !process.env.DATABASE_URL, "needs E2E_EMAIL_OUTBOX and DATABASE_URL"); // prettier-ignore

const PREMIUM_ROUTES = [
  "/api/premium/map",
  "/api/premium/stations/KDFW/hf-current",
  "/api/premium/stations/KDFW/hf?hours=6",
  "/api/premium/stations/KDFW/hf?hours=24",
];

/** Strings that only appear in 5-minute data (never in the free METAR rendering). */
// ("hfmetar" alone is allowed: the public /status block of the status strip is named so.)
const PREMIUM_MARKERS = ['"source":"hfmetar"', "hf_latest", "hf_so_far", "5-MIN", "· reading "];

async function expect403(request: APIRequestContext) {
  for (const r of PREMIUM_ROUTES) {
    const res = await request.get(r);
    expect(res.status(), r).toBe(403);
    expect(res.headers()["cache-control"]).toBe("private, no-store");
    expect(await res.json()).toEqual({ error: "premium_required" });
  }
}

/** The server HTML and the RSC payload of the public pages never contain 5-minute values. */
async function expectNoPremiumInHtml(request: APIRequestContext) {
  for (const path of ["/", "/station/KDFW", "/station/KSEA", "/map"]) {
    for (const headers of [{}, { RSC: "1" }] as Record<string, string>[]) {
      const body = await (await request.get(path, { headers })).text();
      for (const m of PREMIUM_MARKERS) expect(body, `${path} ${JSON.stringify(headers)} has ${m}`).not.toContain(m); // prettier-ignore
    }
  }
}

async function visitPublicPages(page: Page) {
  await page.goto("/station/KDFW");
  await expect(page.getByRole("heading", { name: "Current temperature" })).toBeVisible();
  await page.getByRole("heading", { name: "Observed conditions" }).scrollIntoViewIfNeeded();
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Settlement stations" })).toBeVisible();
  await page.goto("/map");
  await expect(page.getByTestId("map-teaser")).toBeVisible();
  await page.waitForTimeout(1500);
}

async function axe(page: Page, label: string) {
  // Sections below the fold use content-visibility:auto (Phase 6 B1): until scrolled to, they are
  // not laid out and axe would measure their text against whatever lies underneath (the footer).
  await page.addStyleTag({ content: ".below-fold { content-visibility: visible !important; }" });
  const res = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  const bad = res.violations.map((v) => `${v.id}: ${v.nodes.map((n) => `${n.target.join(" ")} ${n.html.slice(0, 120)} ${(n.failureSummary ?? "").slice(0, 160)}`).slice(0, 3).join(" | ")}`); // prettier-ignore
  expect(bad, `axe ${label}`).toEqual([]);
}

test.describe("gating and leaks", () => {
  test("signed out: 403 everywhere, no 5-minute values in HTML/RSC, no Premium or map requests", async ({ page, request }) => {
    await expect403(request);
    await expectNoPremiumInHtml(request);
    const urls = recordRequests(page);
    await visitPublicPages(page);
    expect(urls.filter((u) => u.includes("/api/premium/") || u.includes("openfreemap") || u.includes("/vendor/maplibre"))).toEqual([]);
    await page.goto("/station/KDFW");
    const locked = page.getByRole("button", { name: /5-minute · Premium/ });
    await locked.scrollIntoViewIfNeeded();
    await expect(locked).toHaveAttribute("aria-disabled", "true");
    await expect(page.locator("#chart-teaser")).toContainText("5-minute readings catch peaks and dips between hourly reports.");
    await expect(page.locator("#chart-teaser").getByRole("link", { name: "Start 7-day free trial" })).toHaveAttribute("href", "/signin?mode=signup&next=%2Fpricing");
  }); // prettier-ignore

  for (const state of ["free", "expired"] as BillingCase[]) {
    test(`${state}: 403, no Premium requests, METAR cards and the teaser`, async ({
      page,
    }, info) => {
      await userIn(page, info, state);
      await expect403(page.request);
      await expectNoPremiumInHtml(page.request);
      const urls = recordRequests(page);
      await visitPublicPages(page);
      expect(urls.filter((u) => u.includes("/api/premium/") || u.includes("openfreemap") || u.includes("/vendor/maplibre"))).toEqual([]); // prettier-ignore
      await page.goto("/station/KDFW");
      await expect(page.getByTestId("premium-now")).toHaveCount(0);
      await expect(page.getByText("METAR", { exact: true }).first()).toBeVisible();
      if (!isPhone(page)) {
        await expect(page.getByRole("navigation", { name: "Main" }).getByTestId("pro-pill")).not.toHaveClass(/invisible/); // prettier-ignore
      }
    });
  }

  test("Premium: the same HTML as everyone (values only arrive after load)", async ({
    page,
  }, info) => {
    await userIn(page, info, "trialing");
    await expectNoPremiumInHtml(page.request);
    for (const r of PREMIUM_ROUTES) {
      const res = await page.request.get(r);
      expect(res.status(), r).toBe(200);
      expect(res.headers()["cache-control"]).toBe("private, no-store");
    }
    expect((await page.request.get("/api/premium/stations/KDFW/hf?hours=5")).status()).toBe(400);
    expect((await page.request.get("/api/premium/stations/KZZZ/hf-current")).status()).toBe(400);
  });
});

test.describe("station page, Premium", () => {
  test("5-MIN cards with the B9 lines, METAR comparison, QC exclusion, info button, chart", async ({ page }, info) => {
    await userIn(page, info, "trialing");
    await page.goto("/station/KDFW");
    const now = page.getByTestId("premium-now");
    await expect(now).toBeVisible();
    await expect(now.getByText("5-MIN", { exact: true })).toHaveCount(3);
    await expect(now).toContainText("Premium · 5-minute ASOS data via NOAA MADIS · latest");
    await expect(now).toContainText(/°F unrounded · \d+ °C · reading \d+/);
    await expect(now).toContainText(/Observed \d\d:\d\dZ/);
    await expect(now).toContainText(/Hourly METAR at \d\d:\d\dZ: \d+° \(\d+\.\d\d °F\)/);
    await expect(now).toContainText(/Highest hourly METAR: \d+° \(\d+\.\d\d °F\) at/);
    await expect(now).toContainText("1 reading excluded (QC)");
    await expect(now).toContainText(/Updated \d\d:\d\dZ/);
    const info_ = page.getByRole("button", { name: "About 5-minute data" });
    await info_.click();
    await expect(page.getByRole("note")).toContainText("Not official METAR reports and no METAR quality control.");
    await page.keyboard.press("Escape");
    await expect(page.getByRole("note")).toBeHidden();
    await expect(info_).toBeFocused();
    // chart: 5-minute by default, METAR one click away
    await page.getByRole("heading", { name: "Observed conditions" }).scrollIntoViewIfNeeded();
    await expect(page.getByRole("button", { name: "5-minute", exact: true })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByText(/\d+ five-minute readings in the last 24 h/)).toBeVisible();
    await expect(page.getByText(/; \d+ hourly METAR reports marked/)).toBeVisible();
    await page.getByRole("button", { name: "Hourly METAR", exact: true }).click();
    await expect(page.getByText(/\d+ reports in the last 24 h/)).toBeVisible();
    await expect(page.getByTestId("observed-legend")).toHaveText(/Observed \(5-min\)/, { timeout: 20_000 });
    await axe(page, "station premium");
  }); // prettier-ignore

  test("stale 5-minute data: greyed cards, never METAR numbers inside them", async ({
    page,
  }, info) => {
    await userIn(page, info, "active");
    await page.goto("/station/KSEA");
    const now = page.getByTestId("premium-now");
    await expect(now).toHaveAttribute("data-stale", "true");
    await expect(page.getByText(/5-minute data delayed · last reading .+ ago/)).toBeVisible();
    await expect(now.getByText("5-MIN", { exact: true })).toHaveCount(3);
  });

  test("a station not in the 5-minute feed keeps METAR, with a note", async ({ page }, info) => {
    await userIn(page, info, "trialing");
    await page.goto("/station/KNYC");
    await expect(page.getByText("This station isn't in the 5-minute feed. Values are from the hourly METAR.")).toBeVisible(); // prettier-ignore
    await expect(page.getByTestId("premium-now")).toHaveCount(0);
  });

  test("API error: free cards stay, with a retry note", async ({ page }, info) => {
    await userIn(page, info, "trialing");
    await page.route("**/api/premium/stations/*/hf-current", (r) =>
      r.fulfill({ status: 502, body: "{}" }),
    );
    await page.goto("/station/KDFW");
    await expect(page.getByText("Couldn't load Premium data · retrying")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Current temperature" })).toBeVisible();
    await expect(page.getByTestId("premium-now")).toHaveCount(0);
  });

  test("refresh: every interval while visible, paused when hidden, updated in place", async ({ page }, info) => {
    await userIn(page, info, "trialing");
    await page.addInitScript(() => window.localStorage.setItem("ef:poll-ms", "2000"));
    const hits: number[] = [];
    page.on("request", (r) => { if (r.url().includes("/hf-current")) hits.push(Date.now()); });
    await page.goto("/station/KDFW");
    const card = page.getByTestId("premium-now");
    await expect(card).toBeVisible();
    const handle = await card.elementHandle();
    await page.waitForTimeout(5_500);
    expect(hits.length).toBeGreaterThanOrEqual(3); // first load + at least 2 refreshes
    expect(await handle!.evaluate((el) => el.isConnected)).toBe(true); // same element: updated in place
    await page.evaluate(() => {
      Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
      document.dispatchEvent(new Event("visibilitychange"));
    });
    const hidden = hits.length;
    await page.waitForTimeout(6_000);
    expect(hits.length).toBe(hidden);
    await page.evaluate(() => {
      Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
      document.dispatchEvent(new Event("visibilitychange"));
    });
    await expect.poll(() => hits.length, { timeout: 1_500 }).toBeGreaterThan(hidden); // at once
  }); // prettier-ignore
});

test.describe("billing states", () => {
  test("past_due: Premium plus the banner with the portal button", async ({ page }, info) => {
    await userIn(page, info, "past_due");
    await page.goto("/station/KDFW");
    await expect(page.getByTestId("premium-now")).toBeVisible();
    const banner = page.getByRole("alert").filter({ hasText: "Payment failed. Update your card to keep Premium." });
    await expect(banner).toBeVisible();
    await expect(banner.getByRole("button", { name: "Update card" })).toBeVisible();
    await axe(page, "past_due banner");
  }); // prettier-ignore

  test("cancelled, period not over: Premium plus 'Premium until'", async ({ page }, info) => {
    await userIn(page, info, "canceling");
    await page.goto("/station/KDFW");
    await expect(page.getByTestId("premium-now")).toBeVisible();
    await expect(page.getByTestId("premium-until")).toContainText(/Premium until \w{3} \d+, \d{4}/);
  });

  test("after checkout: 'Activating Premium…' until the mirror says Premium", async ({
    page,
  }, info) => {
    const email = await userIn(page, info, "free");
    await page.goto("/account?checkout=success");
    await expect(page.getByText("Activating Premium…")).toBeVisible();
    await page.waitForTimeout(1_000);
    await expect(page.getByText("Activating Premium…")).toBeVisible(); // nothing granted by the URL
    await setBilling(email, "trialing"); // what the webhook would do
    await expect(page.locator("[data-billing-state]")).toHaveAttribute("data-billing-state", "trialing", { timeout: 15_000 }); // prettier-ignore
  });
});

test.describe("board, Premium", () => {
  test("5-MIN values swapped in; stations outside the feed keep METAR", async ({ page }, info) => {
    await userIn(page, info, "trialing");
    await page.goto("/");
    await expect(page.getByTestId("board-5min").first()).toBeVisible();
    await expect(page.getByText(/5-minute ASOS values \(5-MIN\) where available/)).toBeVisible();
    const nyc = page.getByRole("row").filter({ hasText: "KNYC" });
    await expect(nyc.getByText("5-MIN")).toHaveCount(0);
    await axe(page, "home premium");
  });
});

test.describe("live map", () => {
  test("teaser for signed-out visitors, accessible", async ({ page }) => {
    await page.goto("/map");
    await expect(page.getByTestId("map-teaser")).toBeVisible();
    await expect(page.getByRole("link", { name: "Start 7-day free trial" })).toBeVisible();
    await axe(page, "map teaser");
  });

  test("Premium: outline backup when OpenFreeMap is unreachable, markers, list, panel", async ({ page }, info) => {
    await userIn(page, info, "trialing");
    await blockOpenFreeMap(page);
    await page.goto("/map");
    await expect(page.getByTestId("map-fallback")).toHaveText("Street map unavailable · showing a simple outline", { timeout: 15_000 });
    await expect(page.getByTestId("map-header")).toContainText("5-minute ASOS data for 26 of 28 settlement stations");
    await expect(page.getByTestId("map-list").getByRole("button")).toHaveCount(28);
    await expect(page.getByText("Outline: U.S. Census Bureau cartographic boundaries (public domain)")).toBeAttached();
    // stale and no-5-minute markers
    await expect(page.getByTestId("marker-KSEA")).toHaveAttribute("data-kind", "stale");
    await expect(page.getByTestId("marker-KSEA")).toHaveAttribute("aria-label", /\(delayed\)$/);
    await expect(page.getByTestId("marker-KNYC")).toHaveAttribute("data-kind", "metar");
    // list → panel and marker in sync
    const row = page.getByTestId("map-list").getByRole("button", { name: /^KDFW, / });
    await expect(row).toHaveAttribute("aria-label", /^KDFW, .+, now \d+ °F \(\d+\.\d °F unrounded\) at .+, (Kalshi|Polymarket|Robinhood)/);
    await row.click();
    await expect(page.getByTestId("map-panel")).toContainText("KDFW");
    await expect(page.getByTestId("map-panel")).toContainText(/°F unrounded · \d+ °C · reading/);
    await expect(page.getByTestId("marker-KDFW")).toHaveAttribute("aria-pressed", "true");
    await expect(row).toHaveAttribute("aria-pressed", "true");
    // metric tabs change the list title
    await page.getByRole("group", { name: "Show" }).getByRole("button", { name: "High so far" }).click();
    await expect(page.getByRole("heading", { name: /Highest so far/ })).toBeVisible();
    await page.getByRole("group", { name: "Venue" }).getByRole("button", { name: "Kalshi" }).click();
    await expect(page.getByTestId("map-list").getByRole("button", { name: /^KLGA, / })).toHaveCount(0);
    await axe(page, "map premium");
  }); // prettier-ignore

  test("keyboard: Tab between markers, Enter opens the panel, Esc returns focus", async ({ page }, info) => {
    test.skip(isPhone(page), "phones start zoomed out with clusters (next test)");
    await userIn(page, info, "trialing");
    await blockOpenFreeMap(page);
    await page.goto("/map");
    const dfw = page.getByTestId("marker-KDFW");
    await expect(dfw).toBeVisible({ timeout: 15_000 });
    await dfw.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("map-panel")).toContainText("KDFW");
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("map-panel")).toHaveCount(0);
    await expect(dfw).toBeFocused();
    await page.keyboard.press("Tab");
    const next = await page.evaluate(() => document.activeElement?.getAttribute("data-testid"));
    expect(next).toMatch(/^marker-K/);
    // the New York stations overlap at this zoom: both stay reachable
    for (const id of ["KNYC", "KLGA"]) {
      await page.getByTestId(`marker-${id}`).click();
      await expect(page.getByTestId("map-panel")).toContainText(id);
    }
  }); // prettier-ignore

  test("phone: clusters expand on tap, the list and panel work", async ({ page }, info) => {
    test.skip(!isPhone(page), "desktop shows every marker at the start zoom");
    await userIn(page, info, "trialing");
    await blockOpenFreeMap(page);
    await page.goto("/map");
    const cluster = page.getByTestId("map-cluster").first();
    await expect(cluster).toBeVisible({ timeout: 15_000 });
    await expect(cluster).toHaveAttribute("aria-label", /^\d+ stations here: K/);
    const before = await page.getByTestId("map-cluster").count();
    await cluster.click();
    await expect.poll(async () => (await page.locator("[data-testid^=marker-]:visible").count()), { timeout: 5_000 }).toBeGreaterThan(1);
    expect(await page.getByTestId("map-cluster").count()).toBeLessThanOrEqual(before + 2);
    await page.getByTestId("map-list").getByRole("button", { name: /^KATL, / }).click();
    await expect(page.getByTestId("map-panel")).toContainText("KATL");
  }); // prettier-ignore
});
