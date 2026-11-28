/**
 * What each station shows on the live map for the chosen metric (v2 Phase 10 B5), pure:
 * - in the 5-minute feed → the 5-minute value (delayed data: kept, marked stale);
 * - not in the feed (KNYC, KBKF) → the hourly METAR value, marked METAR.
 */
import type { MapStation } from "@/lib/premium/types";
import { fmtFExact, type TempValue } from "@/lib/temp";
import { formatLocalTime } from "@/lib/time";

export type Metric = "now" | "high" | "low";
export type VenueKey = "all" | "kalshi" | "polymarket" | "robinhood";

export const METRIC_LABEL: Record<Metric, string> = {
  now: "now",
  high: "high so far",
  low: "low so far",
};

export const VENUE_NAME = { kalshi: "Kalshi", polymarket: "Polymarket", robinhood: "Robinhood" };

export interface StationValue {
  temp: TempValue | null;
  /** observation time of the value */
  at: string | null;
  source: "5min" | "metar";
  stale: boolean;
}

export function valueFor(st: MapStation, metric: Metric): StationValue {
  if (st.in_feed) {
    const stale = st.status !== "ok";
    if (metric === "now") {
      const l = st.hf_latest;
      return { temp: l?.temp ?? null, at: l?.observed_at ?? null, source: "5min", stale };
    }
    const e = metric === "high" ? st.hf_so_far.high : st.hf_so_far.low;
    return { temp: e?.temp ?? null, at: e?.observed_at ?? null, source: "5min", stale };
  }
  const m = st.metar;
  const src = metric === "now" ? m.latest : metric === "high" ? m.high_so_far : m.low_so_far;
  return { temp: src?.temp ?? null, at: src?.observed_at ?? null, source: "metar", stale: false };
}

function venueList(st: MapStation): string {
  const v = st.venues.map((x) => VENUE_NAME[x]);
  return v.length <= 1 ? (v[0] ?? "no venue") : `${v.slice(0, -1).join(", ")} and ${v.at(-1)}`;
}

/** e.g. "KDFW, Dallas/Fort Worth, high so far 63 °F (62.6 °F unrounded) at 2:50 PM, Kalshi and Polymarket" */
export function accessibleLabel(st: MapStation, metric: Metric): string {
  const v = valueFor(st, metric);
  const what = METRIC_LABEL[metric];
  const value = v.temp
    ? `${what} ${v.temp.f_rounded} °F (${fmtFExact(v.temp)} °F unrounded)${v.at ? ` at ${formatLocalTime(v.at, st.tz)}` : ""}`
    : `${what} not available`;
  const src = v.source === "metar" ? ", hourly METAR (not in the 5-minute feed)" : "";
  const stale = v.stale ? ", 5-minute data delayed" : "";
  return `${st.station_id}, ${st.name}, ${value}${src}${stale}, ${venueList(st)}`;
}

export function visibleFor(st: MapStation, venue: VenueKey): boolean {
  return venue === "all" || st.venues.includes(venue);
}

/** List order: by value (highest first; no value last) or by station id. */
export function sortStations(list: MapStation[], metric: Metric, by: "value" | "id"): MapStation[] {
  const out = list.slice();
  if (by === "id") return out.sort((a, b) => a.station_id.localeCompare(b.station_id));
  return out.sort((a, b) => {
    const va = valueFor(a, metric).temp?.f_exact;
    const vb = valueFor(b, metric).temp?.f_exact;
    if (va === undefined && vb === undefined) return a.station_id.localeCompare(b.station_id);
    if (va === undefined) return 1;
    if (vb === undefined) return -1;
    return vb - va || a.station_id.localeCompare(b.station_id);
  });
}
