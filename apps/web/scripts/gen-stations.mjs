// Copy the station registry (ids + display names) from data/stations.yaml into
// src/generated/stations.json at build/dev time, so the web build never depends on the API
// being up (owner Phase 5 A4). Run automatically by the predev/prebuild/pretypecheck scripts.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = resolve(here, "../../../data/stations.yaml");
const out = resolve(here, "../src/generated/stations.json");

const yaml = readFileSync(src, "utf8");
const stations = [];
for (const block of yaml.split(/^(?=- id: )/m)) {
  const id = /^- id: (K[A-Z0-9]{3})\s*$/m.exec(block)?.[1];
  if (!id) continue;
  const name = /^ {2}name: "(.*)"\s*$/m.exec(block)?.[1]?.replace(/\\"/g, '"');
  stations.push({ id, name: name ?? id });
}
if (stations.length === 0) throw new Error(`no stations found in ${src}`);
mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, JSON.stringify({ source: "data/stations.yaml", stations }, null, 2) + "\n");
console.log(`gen-stations: ${stations.length} stations → src/generated/stations.json`);
