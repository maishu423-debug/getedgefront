// Lighthouse (mobile by default) N runs per URL; prints the median and the LCP breakdown.
//   node scripts/lh.mjs <outDir> <runs> <url> [url ...]   (env LH_PRESET=desktop for desktop)
//   LH_COOKIE="name=value; ..." audits as a signed-in user (local test accounts only).
// Uses Playwright's Chromium (CHROME_PATH) so no separate Chrome install is needed.
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";

import { chromium } from "@playwright/test";

const [outDir, runsArg, ...urls] = process.argv.slice(2);
const runs = Number(runsArg ?? 3);
const preset = process.env.LH_PRESET === "desktop" ? ["--preset=desktop"] : [];
// headers go through a file: JSON on the command line doesn't survive the Windows shell
const headersFile = `${outDir}/lh-headers.json`;
if (process.env.LH_COOKIE)
  writeFileSync(headersFile, JSON.stringify({ Cookie: process.env.LH_COOKIE }));
const cookie = process.env.LH_COOKIE ? [`--extra-headers=${headersFile}`] : [];
const env = { ...process.env, CHROME_PATH: chromium.executablePath() };
const median = (xs) => [...xs].sort((a, b) => a - b)[Math.floor(xs.length / 2)];

for (const url of urls) {
  const rows = [];
  for (let i = 0; i < runs; i++) {
    const out = `${outDir}/lh_${url.replace(/\W+/g, "_")}_${i}.json`;
    execFileSync(
      process.platform === "win32" ? "pnpm.cmd" : "pnpm",
      ["exec", "lighthouse", url, ...preset, ...cookie, "--output=json", `--output-path=${out}`,
        "--only-categories=performance,accessibility,best-practices,seo",
        "--chrome-flags=--headless=new --no-sandbox", "--quiet"],
      { env, stdio: "ignore", shell: process.platform === "win32" },
    ); // prettier-ignore
    const r = JSON.parse(readFileSync(out, "utf8"));
    const a = r.audits;
    const phases = a["lcp-breakdown-insight"]?.details?.items?.[0]?.items ?? [];
    rows.push({
      perf: Math.round(r.categories.performance.score * 100),
      a11y: Math.round(r.categories.accessibility.score * 100),
      lcp: a["largest-contentful-paint"].numericValue,
      fcp: a["first-contentful-paint"].numericValue,
      tbt: a["total-blocking-time"].numericValue,
      cls: a["cumulative-layout-shift"].numericValue,
      js: (a["resource-summary"]?.details?.items ?? []).find((x) => x.resourceType === "script")
        ?.transferSize,
      fonts: (a["resource-summary"]?.details?.items ?? []).find((x) => x.resourceType === "font"),
      el: a["largest-contentful-paint-element"]?.details?.items?.[0]?.items?.[0]?.node?.snippet,
      phases: phases.map((p) => `${p.subpart ?? p.label}:${Math.round(p.duration)}`).join(" "),
    });
  }
  const m = (k) => median(rows.map((r) => r[k]));
  console.log(
    `${url}  perf ${m("perf")}  a11y ${m("a11y")}  LCP ${(m("lcp") / 1000).toFixed(2)} s  FCP ${(m("fcp") / 1000).toFixed(2)} s  TBT ${Math.round(m("tbt"))} ms  CLS ${m("cls").toFixed(3)}  JS ${Math.round((m("js") ?? 0) / 1024)} KiB`,
  );
  console.log(`  runs: ${rows.map((r) => `${r.perf}/${(r.lcp / 1000).toFixed(1)}s`).join("  ")}`);
  console.log(
    `  fonts: ${rows[0].fonts ? `${rows[0].fonts.requestCount} files, ${Math.round(rows[0].fonts.transferSize / 1024)} KiB` : "?"}`,
  );
  console.log(`  LCP element: ${rows[0].el}`);
  console.log(`  LCP phases: ${rows[0].phases}`);
}
