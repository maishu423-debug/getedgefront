// Builds the bundled backup basemap for /map (v2 Phase 10 B5) from the U.S. Census Bureau's
// cartographic boundary files (2017, public domain) as packaged by us-atlas@3.0.1 (ISC):
//   public/map/us-outline.json  GeoJSON: lower-48 states (fill), the outer edge (coast and
//                               national border) and internal state borders, as lines
//   public/map/us-outline.svg   the same outline as a static picture for the map teaser
// Not part of the build: run once by hand, the outputs are committed (docs/sources.md#map).
// Reads the TopoJSON as data only (its own small decoder below; no third-party code runs).
//
//   npm pack us-atlas@3.0.1   (in an empty scratch folder, then untar)
//   node apps/web/scripts/build-outline.mjs <us-atlas>/package/states-10m.json
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const [statesPath] = process.argv.slice(2);
if (!statesPath) throw new Error("usage: build-outline.mjs <states-10m.json>");
const topo = JSON.parse(readFileSync(statesPath, "utf8"));

// ---- TopoJSON decoding (spec: quantized, delta-encoded arcs; ~i = arc i reversed)
const { scale, translate } = topo.transform;
const arcs = topo.arcs.map((arc) => {
  let x = 0;
  let y = 0;
  return arc.map(([dx, dy]) => {
    x += dx;
    y += dy;
    return [x * scale[0] + translate[0], y * scale[1] + translate[1]];
  });
});
const arcPoints = (i) => (i >= 0 ? arcs[i] : arcs[~i].slice().reverse());
const ring = (ids) => {
  const out = [];
  ids.forEach((i, k) => out.push(...(k ? arcPoints(i).slice(1) : arcPoints(i))));
  return out;
};

// Not lower 48 (+ DC): Alaska, Hawaii and the territories (no settlement station there).
const OUT = new Set(["02", "15", "60", "66", "69", "72", "78"]);
const states = topo.objects.states.geometries.filter(
  (g) => !OUT.has(String(g.id).padStart(2, "0")),
);
const polygonsOf = (g) =>
  g.type === "Polygon" ? [g.arcs] : g.type === "MultiPolygon" ? g.arcs : [];

const use = new Map();
for (const g of states) {
  for (const poly of polygonsOf(g)) {
    for (const r of poly)
      for (const i of r) use.set(i >= 0 ? i : ~i, (use.get(i >= 0 ? i : ~i) ?? 0) + 1);
  }
}

const round = (c) => [Math.round(c[0] * 100) / 100, Math.round(c[1] * 100) / 100];
const clean = (pts) => {
  const out = [];
  for (const p of pts.map(round)) {
    const last = out[out.length - 1];
    if (!last || last[0] !== p[0] || last[1] !== p[1]) out.push(p);
  }
  return out;
};

const polys = [];
for (const g of states) {
  for (const poly of polygonsOf(g)) {
    const rings = poly.map((r) => clean(ring(r))).filter((r) => r.length >= 4);
    if (rings.length) polys.push(rings);
  }
}
const edge = [...use]
  .filter(([, n]) => n === 1)
  .map(([i]) => clean(arcs[i]))
  .filter((l) => l.length >= 2);
const borders = [...use]
  .filter(([, n]) => n > 1)
  .map(([i]) => clean(arcs[i]))
  .filter((l) => l.length >= 2);

const geo = {
  type: "FeatureCollection",
  attribution: "U.S. Census Bureau cartographic boundaries 2017 (public domain), via us-atlas",
  features: [
    {
      type: "Feature",
      properties: { kind: "land" },
      geometry: { type: "MultiPolygon", coordinates: polys },
    },
    {
      type: "Feature",
      properties: { kind: "edge" },
      geometry: { type: "MultiLineString", coordinates: edge },
    },
    {
      type: "Feature",
      properties: { kind: "borders" },
      geometry: { type: "MultiLineString", coordinates: borders },
    },
  ],
};

// ---- SVG: equirectangular with longitude scaled by cos(38°), lower-48 bounding box.
const [lon0, lon1, lat0, lat1] = [-125, -66.5, 24, 49.6];
const k = Math.cos((38 * Math.PI) / 180);
const s = 1000 / ((lon1 - lon0) * k);
// a picture, not a map: ~0.1° steps are plenty
const coarse = (pts) => {
  const out = [];
  for (const p of pts) {
    const r2 = (v) => Math.round(v / 2) * 2; // 2 units ≈ 0.1°
    const q = `${r2((p[0] - lon0) * k * s)} ${r2((lat1 - p[1]) * s)}`;
    if (out[out.length - 1] !== q) out.push(q);
  }
  return out;
};
const landD = polys
  .map((poly) =>
    poly
      .map((r) => coarse(r))
      .filter((r) => r.length >= 3)
      .map((r) => `M${r.join("L")}Z`)
      .join(""),
  )
  .join("");
const lineD = (ls) =>
  ls
    .map((l) => coarse(l))
    .filter((l) => l.length >= 2)
    .map((l) => `M${l.join("L")}`)
    .join("");
const [vw, vh] = [Math.round((lon1 - lon0) * k * s), Math.round((lat1 - lat0) * s)];
const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${vw} ${vh}"><path d="${landD}" fill="#F7F8F4"/><path d="${lineD(borders)}" fill="none" stroke="#D5DCD8" stroke-width="0.8"/><path d="${lineD(edge)}" fill="none" stroke="#B9C4BF" stroke-width="1.5" stroke-linejoin="round"/></svg>\n`;

const outDir = resolve(dirname(fileURLToPath(import.meta.url)), "../public/map");
mkdirSync(outDir, { recursive: true });
const json = JSON.stringify(geo);
writeFileSync(resolve(outDir, "us-outline.json"), json);
writeFileSync(resolve(outDir, "us-outline.svg"), svg);
console.log(
  `us-outline.json ${json.length} bytes, us-outline.svg ${svg.length} bytes, ${polys.length} polygons`,
);
