/**
 * Per-user rate limit for the Premium data routes (v2 Phase 10 B1): fixed window, stored in the
 * same `rateLimit` table as Better Auth's limits, so it survives deploys and restarts. A
 * Premium tab polls three routes about once a minute, so 120/min only stops scripted scraping.
 */
export const PREMIUM_WINDOW_MS = 60_000;
export const PREMIUM_MAX = 120;

export type LimitRow = { count: number; lastRequest: number };

export type LimitStep =
  | { action: "create" | "reset"; row: LimitRow; ok: true }
  | { action: "increment"; row: LimitRow; ok: true }
  | { action: "refuse"; ok: false; retryAfterS: number };

/** Pure: what to do with the stored window for one request at `now`. */
export function limitStep(
  row: LimitRow | null,
  now: number,
  max = PREMIUM_MAX,
  windowMs = PREMIUM_WINDOW_MS,
): LimitStep {
  if (!row) return { action: "create", row: { count: 1, lastRequest: now }, ok: true };
  const start = Number(row.lastRequest);
  if (now - start >= windowMs) {
    return { action: "reset", row: { count: 1, lastRequest: now }, ok: true };
  }
  if (row.count >= max) {
    return { action: "refuse", ok: false, retryAfterS: Math.max(1, Math.ceil((start + windowMs - now) / 1000)) };
  } // prettier-ignore
  return { action: "increment", row: { count: row.count + 1, lastRequest: start }, ok: true };
}
