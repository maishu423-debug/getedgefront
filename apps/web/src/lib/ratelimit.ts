/**
 * Per-IP fixed-window rate limit for the public /api/* proxy routes (Phase 6 B5). In memory: the
 * `web` service runs one instance, so one map is the whole picture. A browser tab polls about
 * three endpoints a minute, so the default of 120/min only stops scripted hammering.
 */
const WINDOW_MS = 60_000;
const buckets = new Map<string, { start: number; count: number }>();
let lastSweep = 0;

export type Verdict = { ok: true; remaining: number } | { ok: false; retryAfterS: number };

export function hit(ip: string, now: number, limit: number): Verdict {
  if (now - lastSweep > WINDOW_MS) {
    for (const [k, b] of buckets) if (now - b.start >= WINDOW_MS) buckets.delete(k);
    lastSweep = now;
  }
  const b = buckets.get(ip);
  if (!b || now - b.start >= WINDOW_MS) {
    buckets.set(ip, { start: now, count: 1 });
    return { ok: true, remaining: limit - 1 };
  }
  b.count += 1;
  if (b.count > limit) {
    return { ok: false, retryAfterS: Math.max(1, Math.ceil((b.start + WINDOW_MS - now) / 1000)) };
  }
  return { ok: true, remaining: limit - b.count };
}

/** Client IP as Railway's edge reports it (X-Real-IP, else the first X-Forwarded-For hop). */
export function clientIp(headers: Headers): string {
  const real = headers.get("x-real-ip")?.trim();
  if (real) return real;
  const fwd = headers.get("x-forwarded-for")?.split(",")[0]?.trim();
  return fwd || "unknown";
}

export function resetForTests(): void {
  buckets.clear();
  lastSweep = 0;
}
