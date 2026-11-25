// Screenshot pages at desktop and phone widths.
//   node scripts/screens.mjs <outDir> [baseUrl] [path ...]
import { chromium } from "@playwright/test";

const [outDir, base = "http://localhost:3000", ...paths] = process.argv.slice(2);
const pages = paths.length
  ? paths
  : ["/", "/station/KDFW", "/station/KBKF", "/pricing", "/sources"];
const widths = [
  ["1440", { width: 1440, height: 900 }],
  ["375", { width: 375, height: 812 }],
];

const browser = await chromium.launch();
for (const [label, viewport] of widths) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  for (const p of pages) {
    await page.goto(base + p, { waitUntil: "networkidle" });
    await page.waitForTimeout(1500); // charts + relative ages after mount
    const name = (p === "/" ? "home" : p.replace(/^\//, "").replaceAll("/", "_")) + `_${label}.png`;
    await page.screenshot({ path: `${outDir}/${name}`, fullPage: true });
    console.log("saved", name);
  }
  await ctx.close();
}
await browser.close();
