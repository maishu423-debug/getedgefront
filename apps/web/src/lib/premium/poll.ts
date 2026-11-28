/**
 * Refresh rules for Premium data (v2 Phase 10 B7), pure so they're unit-tested:
 * - every 60 s plus up to 5 s of jitter (so many tabs don't hit the server in step);
 * - after errors: 2 min, then 5 min (and stays at 5 min) until a request succeeds.
 */
export const POLL_MS = 60_000;
export const JITTER_MS = 5_000;
export const BACKOFF_MS = [120_000, 300_000] as const;

export function nextDelay(failures: number, rand: number, base = POLL_MS): number {
  if (failures <= 0) return base + Math.floor(rand * JITTER_MS * (base / POLL_MS));
  return BACKOFF_MS[Math.min(failures, BACKOFF_MS.length) - 1]!;
}

/** Tests may shorten the interval (never below 2 s) with localStorage "ef:poll-ms". */
export function basePollMs(read: () => string | null): number {
  try {
    const n = Number(read());
    return Number.isFinite(n) && n >= 2_000 ? n : POLL_MS;
  } catch {
    return POLL_MS;
  }
}
