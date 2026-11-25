/**
 * Deployment switches, read at request time on the server (Phase 6 B3/B5). Changing them on
 * Railway restarts the service; no rebuild is needed for these.
 *  - INDEXING_ENABLED=true  → allow search engines (default: off → `X-Robots-Tag: noindex` and a
 *    robots.txt that disallows everything). Turned on only after the owner's "go live".
 *  - CSP_MODE=enforce       → send Content-Security-Policy (default: Content-Security-Policy-
 *    Report-Only, violations go to /api/csp-report and the logs).
 *  - HSTS_ENABLED=true      → send Strict-Transport-Security (only once the custom domain is live).
 *  - RATE_LIMIT_PER_MINUTE  → per-IP limit on /api/* (default 120).
 */
export function indexingEnabled(): boolean {
  return process.env.INDEXING_ENABLED === "true";
}

export function cspMode(): "enforce" | "report-only" {
  return process.env.CSP_MODE === "enforce" ? "enforce" : "report-only";
}

export function hstsEnabled(): boolean {
  return process.env.HSTS_ENABLED === "true";
}

export function rateLimitPerMinute(): number {
  const n = Number(process.env.RATE_LIMIT_PER_MINUTE ?? "120");
  return Number.isFinite(n) && n > 0 ? n : 120;
}

/** One JSON log line (Railway's log view parses JSON). */
export function logJson(level: "info" | "warn" | "error", msg: string, extra: object = {}): void {
  const line = JSON.stringify({
    ts: new Date().toISOString(),
    level: level.toUpperCase(),
    logger: "edgefront.web",
    msg,
    ...extra,
  });
  if (level === "error") console.error(line);
  else console.log(line);
}
