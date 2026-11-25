// Print computed colours for a selector: node scripts/style.mjs <url> <selector>
import { chromium } from "@playwright/test";
const [url, sel] = process.argv.slice(2);
const b = await chromium.launch();
const p = await b.newPage();
await p.goto(url, { waitUntil: "networkidle" });
console.log(
  await p.$$eval(sel, (els) =>
    els
      .slice(0, 3)
      .map(
        (e) =>
          `${e.textContent?.trim().slice(0, 30)} → ${getComputedStyle(e).color} | class=${e.getAttribute("class")}`,
      ),
  ),
);
await b.close();
