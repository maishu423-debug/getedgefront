// Legal pages (v2 Part 2): copies content/legal/{terms,privacy,refund}.md into
// src/generated/legal.json for /terms, /privacy and /refund, and refuses to build while any owner
// placeholder is left: "[OWNER: ...]" (the owner's details) or "[VERIFY: ...]" (a fact still to be
// settled). Production builds and CI fail here until every one is filled in.
//   node scripts/gen-legal.mjs          build: fails on placeholders unless ALLOW_LEGAL_PLACEHOLDERS=1
//   node scripts/gen-legal.mjs --allow  dev / typecheck: lists them as a warning only
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
// LEGAL_DIR / LEGAL_OUT: tests only (a temporary folder instead of the real documents)
const dir = process.env.LEGAL_DIR ?? resolve(here, "../content/legal");
const out = process.env.LEGAL_OUT ?? resolve(here, "../src/generated/legal.json");
const DOCS = ["terms", "privacy", "refund"];
const PLACEHOLDER = /\[(OWNER|VERIFY):[^\]]*\]/g;

export function findPlaceholders(text) {
  const found = [];
  text.split("\n").forEach((line, i) => {
    for (const m of line.matchAll(PLACEHOLDER)) found.push({ line: i + 1, text: m[0] });
  });
  return found;
}

const docs = {};
const left = [];
for (const name of DOCS) {
  const md = readFileSync(resolve(dir, `${name}.md`), "utf8");
  if (/<!--/.test(md)) throw new Error(`${name}.md still has an HTML comment block`);
  docs[name] = md;
  for (const p of findPlaceholders(md)) left.push(`${name}.md:${p.line}  ${p.text.slice(0, 110)}`);
}
mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, JSON.stringify(docs) + "\n");

const allow = process.argv.includes("--allow") || process.env.ALLOW_LEGAL_PLACEHOLDERS === "1";
if (left.length) {
  const msg = `gen-legal: ${left.length} placeholder(s) left in content/legal:\n  ${left.join("\n  ")}`;
  if (!allow) {
    console.error(`${msg}\nThe legal pages can't be published until the owner fills these in.`);
    process.exit(1);
  }
  console.warn(`${msg}\n(allowed for this run only)`);
} else {
  console.log("gen-legal: 3 documents, no placeholders left");
}
