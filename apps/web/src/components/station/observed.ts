/** Pure helpers for the observed chart (deterministic: anchored to the API's generated_at). */

import { findGaps, type GapMs } from "@/lib/gaps";
import { formatLocalTime, formatZulu } from "@/lib/time";
import type { ObservedPoint, ObservedResponse } from "@/lib/types";
import { cToFDisplay } from "@/lib/units";

export interface Prepared {
  startMs: number;
  endMs: number;
  points: (ObservedPoint & { t: number })[];
  gaps: GapMs[];
}

export function prepare(data: ObservedResponse, hours: 6 | 24): Prepared {
  const endMs = Date.parse(data.generated_at);
  const startMs = endMs - hours * 3600_000;
  const points = data.points
    .map((p) => ({ ...p, t: Date.parse(p.observed_at) }))
    .filter((p) => p.t >= startMs && p.t <= endMs);
  return {
    startMs,
    endMs,
    points,
    gaps: findGaps(
      points.map((p) => p.t),
      startMs,
      endMs,
      data.gap_minutes,
    ),
  };
}

/** Accessible text summary, e.g. "24 reports (2 SPECI) in the last 24 h; temperature ranged 40–57 °F…". */
export function summarize(p: Prepared, hours: number, tz: string): string {
  if (!p.points.length) return `No METAR reports in the last ${hours} h.`;
  const speci = p.points.filter((x) => x.report_type === "SPECI").length;
  const parts = [
    `${p.points.length} reports${speci ? ` (${speci} SPECI)` : ""} in the last ${hours} h`,
  ];
  const temps = p.points.filter((x) => x.temp_c !== null);
  if (temps.length) {
    const hi = temps.reduce((a, b) => (b.temp_c! > a.temp_c! ? b : a));
    const lo = temps.reduce((a, b) => (b.temp_c! < a.temp_c! ? b : a));
    parts.push(
      `temperature ranged ${cToFDisplay(lo.temp_c)}–${cToFDisplay(hi.temp_c)} °F, highest at ${formatZulu(hi.observed_at)} (${formatLocalTime(hi.observed_at, tz)})`,
    );
  }
  const gusts = p.points.filter((x) => x.gust_kt !== null);
  if (gusts.length) {
    const g = gusts.reduce((a, b) => (b.gust_kt! > a.gust_kt! ? b : a));
    parts.push(`peak gust ${g.gust_kt} kt at ${formatZulu(g.observed_at)}`);
  }
  if (p.gaps.length) {
    parts.push(
      `${p.gaps.length} gap${p.gaps.length > 1 ? "s" : ""} with no reports (${p.gaps
        .map(
          (g) =>
            `${formatZulu(new Date(g.startMs).toISOString())}–${formatZulu(new Date(g.endMs).toISOString())}`,
        )
        .join(", ")})`,
    );
  }
  return parts.join("; ") + ".";
}
