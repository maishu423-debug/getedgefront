// Lists elements that overflow a 375 px viewport outside any scroll container.
//   node scripts/overflow.mjs <url>
import { chromium } from "@playwright/test";
const url = process.argv[2];
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 375, height: 800 } });
await p.goto(url, { waitUntil: "networkidle" });
await p.waitForTimeout(1000);
const r = await p.evaluate(() => {
  const out = [];
  const W = document.documentElement.clientWidth;
  for (const el of document.querySelectorAll("body *")) {
    const rc = el.getBoundingClientRect();
    if (rc.right > W + 1 && rc.width > 0) {
      let a = el.parentElement,
        scrolls = false;
      while (a) {
        const s = getComputedStyle(a);
        if (["auto", "scroll", "hidden"].includes(s.overflowX)) {
          scrolls = true;
          break;
        }
        a = a.parentElement;
      }
      if (!scrolls)
        out.push(
          `${el.tagName.toLowerCase()}.${(el.className?.baseVal ?? el.className ?? "").toString().slice(0, 60)} right=${Math.round(rc.right)} w=${Math.round(rc.width)}`,
        );
    }
  }
  return { W, scrollW: document.documentElement.scrollWidth, out: out.slice(0, 12) };
});
console.log(JSON.stringify(r, null, 1));
await b.close();
