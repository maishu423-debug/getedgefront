// Fail if anything that looks like a server secret ended up in the browser bundle (Phase 6 B3).
//   node scripts/check-bundle.mjs   (after `next build`)
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const ROOT = new URL("../.next/static/", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
const NEEDLES = [
  "CONTACT_EMAIL", "DATABASE_URL", "API_INTERNAL_URL", "BACKUP_S3", "postgresql://",
  "postgres://", "railway.internal", "INDEXING_ENABLED", "RATE_LIMIT_PER_MINUTE",
]; // prettier-ignore
const EMAIL = /[A-Za-z0-9._%+-]+@(?!example\.)[A-Za-z0-9.-]+\.(?:com|org|net|io|edu|gov)\b/g;

function* files(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) yield* files(p);
    else if (/\.(js|css|json|html)$/.test(name)) yield p;
  }
}

const hits = [];
for (const f of files(ROOT)) {
  const text = readFileSync(f, "utf8");
  for (const n of NEEDLES) if (text.includes(n)) hits.push(`${f}: ${n}`);
  for (const m of text.match(EMAIL) ?? []) hits.push(`${f}: email-like string ${m}`);
}
if (hits.length) {
  console.error("Possible secrets in the client bundle:\n" + hits.join("\n"));
  process.exit(1);
}
console.log(`client bundle clean (${NEEDLES.length} secret names + email pattern checked)`);
