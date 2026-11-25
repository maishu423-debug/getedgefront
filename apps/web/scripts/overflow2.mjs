import { chromium } from "@playwright/test";
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 375, height: 800 } });
await p.goto(process.argv[2], { waitUntil: "networkidle" });
await p.waitForTimeout(1000);
console.log(
  JSON.stringify(
    await p.evaluate(() =>
      [...document.querySelectorAll("*")]
        .filter((e) => !e.closest("table"))
        .map((el) => ({ el, r: el.getBoundingClientRect() }))
        .filter((x) => x.r.right > 376)
        .sort((a, b) => b.r.right - a.r.right)
        .slice(0, 8)
        .map(
          ({ el, r }) =>
            `${el.tagName.toLowerCase()} pos=${getComputedStyle(el).position} right=${Math.round(r.right)} cls=${(el.getAttribute("class") || "").slice(0, 70)}`,
        ),
    ),
    null,
    1,
  ),
);
await b.close();
