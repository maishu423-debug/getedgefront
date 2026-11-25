// Capture every UI state from deliberately degraded backends (owner Phase 4 C).
//   node scripts/states.mjs <outDir>
// Expects: 3100 = API unreachable, 3101 = empty DB, 3102 = day-old DB (stale),
//          3103 = API behind a 6 s delay (loading skeletons), 3000 = live.
import { chromium } from "@playwright/test";

const out = process.argv[2];
const shots = [
  ["upstream_down_home", "http://localhost:3100/", "networkidle"],
  ["upstream_down_station", "http://localhost:3100/station/KDFW", "networkidle"],
  ["no_data_home", "http://localhost:3101/", "networkidle"],
  ["no_data_station", "http://localhost:3101/station/KDFW", "networkidle"],
  ["stale_home", "http://localhost:3102/", "networkidle"],
  ["stale_station", "http://localhost:3102/station/KDFW", "networkidle"],
  ["loading_home", "http://localhost:3103/", "commit"],
  ["loading_station", "http://localhost:3103/station/KDFW", "commit"],
  ["not_available_KBKF", "http://localhost:3000/station/KBKF", "networkidle"],
  ["not_found_KZZZ", "http://localhost:3000/station/KZZZ", "networkidle"],
];

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
for (const [name, url, wait] of shots) {
  await page.goto(url, { waitUntil: wait });
  await page.waitForTimeout(wait === "commit" ? 1200 : 1500);
  await page.screenshot({ path: `${out}/${name}.png`, fullPage: wait !== "commit" });
  console.log("saved", name);
}
await browser.close();
