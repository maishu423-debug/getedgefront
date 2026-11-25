// Screenshot the model guidance section (and the full page) for stations at desktop + phone.
//   node scripts/model-shots.mjs <outDir> [baseUrl] [station ...]
import { chromium } from "@playwright/test";

const [outDir, base = "http://localhost:3000", ...ids] = process.argv.slice(2);
const stations = ids.length ? ids : ["KDFW", "KMIA"];
const widths = [
  ["1440", { width: 1440, height: 900 }],
  ["375", { width: 375, height: 812 }],
];

const browser = await chromium.launch();
for (const [label, viewport] of widths) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  for (const id of stations) {
    await page.goto(`${base}/station/${id}`, { waitUntil: "networkidle" });
    const section = page.locator("section", {
      has: page.getByRole("heading", { name: /^Model guidance for / }),
    });
    await section.scrollIntoViewIfNeeded();
    await section
      .locator("canvas")
      .first()
      .waitFor({ timeout: 15000 })
      .catch(() => {});
    await page.waitForTimeout(1200);
    await section.screenshot({ path: `${outDir}/${id}_models_${label}.png` });
    await page.screenshot({ path: `${outDir}/${id}_page_${label}.png`, fullPage: true });
    console.log("saved", id, label);
  }
  await ctx.close();
}
await browser.close();
