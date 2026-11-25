/**
 * Climate day in TypeScript, mirroring edgefront_core.climate (LST basis): midnight to midnight
 * local *standard* time, so during DST it ends at 1:00 AM on the local clock. Always computed
 * from the station's IANA zone, never the browser's.
 */

const MIN = 60_000;

/** UTC offset (minutes) of `tz` at instant `ms`, e.g. -300 for EST. */
export function offsetMinutes(tz: string, ms: number): number {
  const part = new Intl.DateTimeFormat("en-US", { timeZone: tz, timeZoneName: "longOffset" })
    .formatToParts(new Date(ms))
    .find((p) => p.type === "timeZoneName")?.value;
  if (!part || part === "GMT") return 0;
  const m = /GMT([+-])(\d{2}):?(\d{2})?/.exec(part);
  if (!m) return 0;
  const v = Number(m[2]) * 60 + Number(m[3] ?? 0);
  return m[1] === "-" ? -v : v;
}

/** Standard-time offset for the year of `ms`: the smaller of the January/July offsets
 * (all U.S. zones are northern-hemisphere; Phoenix has no DST and both are equal). */
export function standardOffsetMinutes(tz: string, ms: number): number {
  const y = new Date(ms).getUTCFullYear();
  return Math.min(offsetMinutes(tz, Date.UTC(y, 0, 15)), offsetMinutes(tz, Date.UTC(y, 6, 15)));
}

export interface ClimateBounds {
  date: string; // YYYY-MM-DD (local standard date)
  startMs: number;
  endMs: number;
}

export function climateDayBounds(nowMs: number, tz: string): ClimateBounds {
  const std = standardOffsetMinutes(tz, nowMs);
  const lst = new Date(nowMs + std * MIN);
  const y = lst.getUTCFullYear();
  const mo = lst.getUTCMonth();
  const d = lst.getUTCDate();
  const startMs = Date.UTC(y, mo, d) - std * MIN;
  return {
    date: `${y}-${String(mo + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`,
    startMs,
    endMs: startMs + 24 * 60 * MIN,
  };
}

/** "3 h 10 m" until `endMs` (never negative). */
export function formatCountdown(endMs: number, nowMs: number): string {
  const mins = Math.max(0, Math.ceil((endMs - nowMs) / MIN));
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return h ? `${h} h ${m} m` : `${m} m`;
}

export function elapsedFraction(b: ClimateBounds, nowMs: number): number {
  return Math.min(1, Math.max(0, (nowMs - b.startMs) / (b.endMs - b.startMs)));
}
