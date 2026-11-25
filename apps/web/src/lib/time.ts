/**
 * Time formatting. Server and client produce identical strings for the same instant and time
 * zone (no "now" involved), so these are safe during SSR. Relative ages depend on "now" and are
 * only rendered after mount (see components/RelativeAge.tsx).
 */

/** "2026-11-24T21:05:12Z" → "21:05Z". "—" for missing/invalid input (never invents a time). */
export function formatZulu(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}Z`;
}

function valid(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** Station-local clock time, e.g. "1:51 PM". */
export function formatLocalTime(iso: string | null | undefined, tz: string): string {
  const d = valid(iso);
  if (!d) return "—";
  return new Intl.DateTimeFormat("en-US", {
    timeZone: tz,
    hour: "numeric",
    minute: "2-digit",
  }).format(d);
}

/** Time-zone abbreviation at that instant, e.g. "CST" / "CDT". */
export function tzAbbrev(iso: string | null | undefined, tz: string): string {
  const d = valid(iso) ?? new Date(0);
  const part = new Intl.DateTimeFormat("en-US", { timeZone: tz, timeZoneName: "short" })
    .formatToParts(d)
    .find((p) => p.type === "timeZoneName");
  return part?.value ?? tz;
}

/** "1:51 PM CST". */
export function formatLocalWithZone(iso: string | null | undefined, tz: string): string {
  return valid(iso) ? `${formatLocalTime(iso, tz)} ${tzAbbrev(iso, tz)}` : "—";
}

/** "Nov 24". */
export function formatShortDate(isoDate: string): string {
  const [y, m, d] = isoDate.split("-").map(Number);
  if (!y || !m || !d) return "—";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(y, m - 1, d)));
}

/** "14:07" (24 h, as in the products) → "2:07 PM". */
export function hhmmTo12h(hhmm: string | null | undefined): string {
  if (!hhmm) return "—";
  const m = /^(\d{1,2}):(\d{2})$/.exec(hhmm);
  if (!m) return hhmm;
  let h = Number(m[1]);
  const ap = h >= 12 && h < 24 ? "PM" : "AM";
  h = h % 12 || 12;
  return `${h}:${m[2]} ${ap}`;
}

/** "just now", "12 min ago", "2 h 5 min ago", "3 d ago". Future → "just now". */
export function relativeAge(iso: string | null | undefined, nowMs: number): string {
  const d = valid(iso);
  if (!d) return "—";
  const mins = Math.floor((nowMs - d.getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const h = Math.floor(mins / 60);
  if (h < 48) {
    const m = mins % 60;
    return m ? `${h} h ${m} min ago` : `${h} h ago`;
  }
  return `${Math.floor(h / 24)} d ago`;
}

export function minutesSince(iso: string | null | undefined, nowMs: number): number | null {
  const d = valid(iso);
  return d ? Math.floor((nowMs - d.getTime()) / 60000) : null;
}
