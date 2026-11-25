import { chromium } from "@playwright/test";
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 375, height: 800 } });
await p.goto(process.argv[2], { waitUntil: "networkidle" });
await p.waitForTimeout(1000);
console.log(
  JSON.stringify(
    await p.evaluate(() => {
      const t = document.querySelector("table");
      const out = [];
      let a = t;
      while (a) {
        const s = getComputedStyle(a);
        out.push(
          `${a.tagName.toLowerCase()} w=${Math.round(a.getBoundingClientRect().width)} sw=${a.scrollWidth} ox=${s.overflowX} disp=${s.display} flex=${s.flex} minw=${s.minWidth}`,
        );
        a = a.parentElement;
      }
      return out;
    }),
    null,
    1,
  ),
);
await b.close();
