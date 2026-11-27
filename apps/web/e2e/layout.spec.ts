import { expect, type Page, test } from "@playwright/test";

/** Layout-shift scores since navigation (buffered), after things settle: whole page and the
 * part caused by elements inside the header. */
async function shifts(page: Page): Promise<{ total: number; header: number }> {
  return page.evaluate(
    () =>
      new Promise<{ total: number; header: number }>((resolve) => {
        const out = { total: 0, header: 0 };
        type Shift = { value: number; hadRecentInput: boolean; sources: { node?: Node }[] };
        new PerformanceObserver((list) => {
          for (const e of list.getEntries() as unknown as Shift[]) {
            if (e.hadRecentInput) continue;
            out.total += e.value;
            const header = document.querySelector("header");
            if (e.sources.some((s) => s.node && header?.contains(s.node))) out.header += e.value;
          }
        }).observe({ type: "layout-shift", buffered: true });
        setTimeout(() => resolve(out), 1500);
      }),
  );
}

const isPhone = (page: Page) => (page.viewportSize()?.width ?? 1440) < 640;

test.describe("layout stability", () => {
  test("home: the data-status strip is one 38 px line and the page doesn't shift", async ({
    page,
  }) => {
    await page.goto("/");
    const strip = page.getByTestId("status-strip");
    await expect(strip).toBeVisible();
    const score = (await shifts(page)).total;
    expect((await strip.boundingBox())?.height).toBe(38);
    // one line: no item sits below the first one
    const tops = await strip.evaluate((el) =>
      [...el.children].map((c) => Math.round(c.getBoundingClientRect().top)),
    );
    expect(new Set(tops).size).toBe(1);
    expect(score, "CLS on /").toBeLessThan(0.05);
  });

  test("header is one fixed-height row; the menu works below 640 px", async ({ page }) => {
    await page.goto("/sources");
    const header = page.getByRole("banner");
    const menuButton = header.getByRole("button", { name: "Menu" });
    if (!isPhone(page)) {
      await expect(menuButton).toBeHidden();
      await expect(header.getByRole("navigation", { name: "Main" })).toBeVisible();
      return;
    }
    expect((await header.boundingBox())?.height).toBe(65); // 64 px row + 1 px border
    const cls = await shifts(page);
    expect(cls.header, "shift caused by the header").toBe(0);
    expect(cls.total, "CLS on /sources").toBeLessThan(0.05);
    await expect(header.getByRole("link", { name: "Sign in", exact: true })).toBeVisible();
    await expect(menuButton).toHaveAttribute("aria-expanded", "false");
    const panelId = await menuButton.getAttribute("aria-controls");
    expect(panelId).toBeTruthy();

    // open: focus moves into the panel
    await menuButton.click();
    await expect(menuButton).toHaveAttribute("aria-expanded", "true");
    const panel = page.locator(`[id="${panelId}"]`);
    await expect(panel).toBeVisible();
    await expect(panel.getByRole("link", { name: "Stations" })).toBeFocused();
    for (const name of ["Stations", "Sources", "Pricing", "Start free trial"])
      await expect(panel.getByRole("link", { name, exact: true })).toBeVisible();
    await expect(panel.getByRole("link", { name: /Map/ })).toContainText("PRO");
    await expect(panel.getByRole("link", { name: "Sources" })).toHaveAttribute(
      "aria-current",
      "page",
    );

    // Esc closes and returns focus to the button
    await page.keyboard.press("Escape");
    await expect(panel).toBeHidden();
    await expect(menuButton).toBeFocused();
    await expect(menuButton).toHaveAttribute("aria-expanded", "false");

    // keyboard: nothing is trapped — Tab walks through the panel and out of it, which closes it
    await page.keyboard.press("Enter");
    await expect(panel).toBeVisible();
    for (let i = 0; i < 8; i++) await page.keyboard.press("Tab");
    await expect(panel).toBeHidden();
    await expect(menuButton).toHaveAttribute("aria-expanded", "false");

    // choosing a link navigates and closes the menu
    await menuButton.click();
    await panel.getByRole("link", { name: "Pricing" }).click();
    await expect(page).toHaveURL(/\/pricing$/);
    await expect(page.getByRole("banner").getByRole("button", { name: "Menu" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });
});
