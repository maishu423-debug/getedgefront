// MapLibre GL JS runs its tile work in a module worker, which it finds next to its own file.
// The bundler moves that file, so the worker is served from public/vendor instead (same origin,
// so the CSP needs no extra host), named with the version so a release never serves a stale
// copy. Run by predev/prebuild; public/vendor is not committed.
import { copyFileSync, mkdirSync, readdirSync, rmSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const pkgPath = require.resolve("maplibre-gl/package.json");
const { version } = require(pkgPath);
const src = resolve(dirname(pkgPath), "dist/maplibre-gl-worker.mjs");
const outDir = resolve(here, "../public/vendor");
mkdirSync(outDir, { recursive: true });
for (const f of readdirSync(outDir))
  if (f.startsWith("maplibre-gl-worker-")) rmSync(resolve(outDir, f));
copyFileSync(src, resolve(outDir, `maplibre-gl-worker-${version}.mjs`));
console.log(`copy-maplibre-worker: maplibre-gl-worker-${version}.mjs → public/vendor`);
