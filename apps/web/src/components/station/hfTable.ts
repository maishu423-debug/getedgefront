/**
 * Rows of the "5-minute readings" table (v2 Phase 10b Part 1), pure: newest first, a divider at
 * each UTC hour ("21Z · 3 PM"), and one muted row for each stretch with no readings ("No readings
 * 14:05–14:25Z") so a gap is never skipped silently or filled in.
 */
import type { HfReading } from "@/lib/premium/types";
import { formatLocalTime, formatZulu } from "@/lib/time";

export const CADENCE_MS = 5 * 60_000;

export type TableItem =
  | { kind: "hour"; key: string; label: string }
  | { kind: "gap"; key: string; from: string; to: string; label: string }
  | { kind: "row"; key: string; r: HfReading };

function hourLabel(t: number, tz: string): string {
  const iso = new Date(t).toISOString();
  const local = formatLocalTime(iso, tz).replace(/:00 /, " ");
  return `${iso.slice(11, 13)}Z · ${local}`;
}

/** `readings` in any order; keeps those within `hours` of the newest. */
export function tableItems(readings: HfReading[], hours: number, tz: string): TableItem[] {
  const sorted = readings
    .map((r) => ({ r, t: Date.parse(r.observed_at) }))
    .sort((a, b) => b.t - a.t);
  if (!sorted.length) return [];
  const cutoff = sorted[0]!.t - hours * 3600_000;
  const rows = sorted.filter((x) => x.t > cutoff);
  const out: TableItem[] = [];
  let hour = -1;
  rows.forEach((x, i) => {
    const h = Math.floor(x.t / 3600_000);
    if (h !== hour) {
      out.push({ kind: "hour", key: `h${h}`, label: hourLabel(h * 3600_000, tz) });
      hour = h;
    }
    out.push({ kind: "row", key: x.r.observed_at, r: x.r });
    const next = rows[i + 1];
    if (next && x.t - next.t > CADENCE_MS) {
      const from = new Date(next.t + CADENCE_MS).toISOString();
      const to = new Date(x.t - CADENCE_MS).toISOString();
      out.push({
        kind: "gap",
        key: `g${from}`,
        from,
        to,
        label:
          from === to
            ? `No reading at ${formatZulu(from)}`
            : `No readings ${formatZulu(from)}–${formatZulu(to)}`,
      });
    }
  });
  return out;
}

/** MADIS data descriptors (docs/formats/hfmetar.md, MADIS surface QC notes). */
export const QC_MEANING: Record<string, string> = {
  Z: "preliminary, no quality control yet",
  C: "coarse pass: passed the validity check",
  S: "screened: passed the validity and consistency checks",
  V: "verified: passed all checks, including neighbouring stations",
  X: "rejected: failed the validity check",
  Q: "questioned: passed the validity check but failed a consistency or neighbour check",
  G: "subjectively good",
  B: "subjectively bad",
};

/** QC-failed (owner rule): left out of the 5-minute high/low and marked in the table. */
export const QC_FLAGGED = new Set(["X", "Q", "B"]);
