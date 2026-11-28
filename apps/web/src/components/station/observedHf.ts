/** Pure helpers for the 5-minute view of the observed chart (v2 Phase 10 B3). */

import { findGaps, type GapMs } from "@/lib/gaps";
import type { HfReading, HfSeriesResponse } from "@/lib/premium/types";
import { cToFExact, fmtFExact, fmtPossible } from "@/lib/temp";
import { formatLocalTime, formatZulu } from "@/lib/time";
import type { ObservedResponse } from "@/lib/types";

/** A line is never drawn across more than two missed readings' worth of time. */
export const HF_CADENCE_MIN = 5;
export const HF_GAP_MIN = 2 * HF_CADENCE_MIN;
/** The newest reading is "late" (stale) after this long: matches the API's 30-minute rule. */
export const HF_LATE_MIN = 30;

export interface HfPoint extends HfReading {
  t: number;
  /** °F exactly as converted (f_exact), what the line plots */
  tempF: number | null;
  dewF: number | null;
  rh: number | null;
}

export interface MetarDot {
  t: number;
  tempF: number;
  observed_at: string;
  report_type: string;
}

export interface PreparedHf {
  startMs: number;
  endMs: number;
  points: HfPoint[];
  gaps: GapMs[];
  metar: MetarDot[];
}

/** Relative humidity from temperature and dew point (Magnus), like the API's rh_computed. */
export function rhFrom(tc: number | null, dc: number | null): number | null {
  if (tc === null || dc === null) return null;
  const e = (x: number) => Math.exp((17.625 * x) / (243.04 + x));
  return Math.max(0, Math.min(100, Math.round((100 * e(dc)) / e(tc))));
}

export function prepareHf(
  hf: HfSeriesResponse,
  observed: ObservedResponse | null,
  hours: 6 | 24,
): PreparedHf {
  const endMs = Date.parse(hf.generated_at);
  const startMs = endMs - hours * 3600_000;
  const points = hf.readings
    .map((r) => ({
      ...r,
      t: Date.parse(r.observed_at),
      tempF: r.temp ? r.temp.f_exact : null,
      dewF: r.dewpt_c !== null ? cToFExact(r.dewpt_c) : null,
      rh: rhFrom(r.temp_c, r.dewpt_c),
    }))
    .filter((p) => p.t >= startMs && p.t <= endMs);
  const metar = (observed?.points ?? [])
    .filter((p) => p.temp_c !== null)
    .map((p) => ({
      t: Date.parse(p.observed_at),
      tempF: cToFExact(p.temp_c!),
      observed_at: p.observed_at,
      report_type: p.report_type,
    }))
    .filter((p) => p.t >= startMs && p.t <= endMs);
  // A reading reaches us 10-20 min after it was observed (MADIS upstream), so the stretch from
  // the newest reading to "now" is only called a gap once the data is really late.
  const last = points.at(-1)?.t;
  const edge = last !== undefined && endMs - last <= HF_LATE_MIN * 60_000 ? last : endMs;
  return {
    startMs,
    endMs,
    points,
    metar,
    gaps: findGaps(
      points.map((p) => p.t),
      startMs,
      edge,
      HF_GAP_MIN,
    ),
  };
}

/** Accessible text summary of the 5-minute view (design `summary`). */
export function summarizeHf(p: PreparedHf, hours: number, tz: string): string {
  if (!p.points.length) return `No 5-minute readings in the last ${hours} h.`;
  const parts = [`${p.points.length} five-minute readings in the last ${hours} h`];
  const usable = p.points.filter((x) => x.temp && !x.qc_failed);
  if (usable.length) {
    const hi = usable.reduce((a, b) => (b.temp!.f_exact > a.temp!.f_exact ? b : a));
    const lo = usable.reduce((a, b) => (b.temp!.f_exact < a.temp!.f_exact ? b : a));
    parts.push(
      `temperature ranged ${lo.temp!.f_rounded}–${hi.temp!.f_rounded} °F (${fmtFExact(lo.temp!)}–${fmtFExact(hi.temp!)} °F unrounded), highest at ${formatZulu(hi.observed_at)} (${formatLocalTime(hi.observed_at, tz)})`,
    );
  }
  const qc = p.points.filter((x) => x.qc_failed).length;
  if (qc) parts.push(`${qc} reading${qc > 1 ? "s" : ""} flagged by MADIS quality control`);
  if (p.metar.length) parts.push(`${p.metar.length} hourly METAR reports marked`);
  if (p.gaps.length) {
    parts.push(
      `${p.gaps.length} gap${p.gaps.length > 1 ? "s" : ""} with no readings (${p.gaps
        .map(
          (g) =>
            `${formatZulu(new Date(g.startMs).toISOString())}–${formatZulu(new Date(g.endMs).toISOString())}`,
        )
        .join(", ")})`,
    );
  }
  return parts.join("; ") + ".";
}

/** Tooltip rows for one 5-minute reading (B9 rounded + unrounded, °C, possible readings, QC). */
export function hfTooltip(x: HfPoint, tz: string): string[] {
  const rows = [
    `<b>5-minute ${formatZulu(x.observed_at)}</b> (${formatLocalTime(x.observed_at, tz)})`,
  ];
  if (x.temp) {
    const reading = x.temp.precision === "whole_c" ? fmtPossible(x.temp) : "";
    rows.push(
      `Temp ${x.temp.f_rounded}°F (${fmtFExact(x.temp)} °F unrounded) · ${Math.round(x.temp.c)} °C`,
    );
    if (reading) rows.push(`Station reading ${reading}`);
  } else {
    rows.push(x.temp_c !== null ? `Temp ${x.temp_c} °C (not on the expected grid)` : "Temp —");
  }
  rows.push(`Dew pt ${x.dewF !== null ? `${x.dewF.toFixed(1)} °F unrounded` : "—"}`);
  rows.push(`Wind ${x.wind_kt === null ? "—" : `${x.wind_dir_deg ?? "—"}° ${x.wind_kt} kt${x.gust_kt ? ` G${x.gust_kt}` : ""}`}`); // prettier-ignore
  if (x.qc_temp && x.qc_temp !== "V") {
    rows.push(`QC ${x.qc_temp}${x.qc_failed ? " · left out of the high/low" : ""}`);
  }
  return rows;
}
