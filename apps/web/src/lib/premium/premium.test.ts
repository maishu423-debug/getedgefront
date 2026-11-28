import { describe, expect, it } from "vitest";

import { prepareHf, rhFrom, summarizeHf, HF_GAP_MIN } from "@/components/station/observedHf";
import type { ObservedResponse } from "@/lib/types";

import { limitStep, PREMIUM_MAX } from "./limit";
import { basePollMs, nextDelay, POLL_MS } from "./poll";
import type { HfReading, HfSeriesResponse } from "./types";

describe("per-user Premium rate limit (B1)", () => {
  const t0 = 1_000_000;
  it("creates, counts up to the limit, refuses with a Retry-After, then resets", () => {
    expect(limitStep(null, t0)).toEqual({ action: "create", row: { count: 1, lastRequest: t0 }, ok: true });
    let row = { count: 1, lastRequest: t0 };
    for (let i = 2; i <= PREMIUM_MAX; i++) {
      const s = limitStep(row, t0 + i);
      expect(s.ok).toBe(true);
      if (s.ok) row = s.row;
    }
    expect(row).toEqual({ count: PREMIUM_MAX, lastRequest: t0 });
    expect(limitStep(row, t0 + 15_000)).toEqual({ action: "refuse", ok: false, retryAfterS: 45 });
    expect(limitStep(row, t0 + 60_000)).toEqual({ action: "reset", row: { count: 1, lastRequest: t0 + 60_000 }, ok: true });
  }); // prettier-ignore
});

describe("refresh schedule (B7)", () => {
  it("60 s plus up to 5 s of jitter while all is well", () => {
    expect(nextDelay(0, 0)).toBe(POLL_MS);
    expect(nextDelay(0, 0.999)).toBe(POLL_MS + 4_995);
  });
  it("backs off 2 min, then 5 min, and stays there", () => {
    expect(nextDelay(1, 0.5)).toBe(120_000);
    expect(nextDelay(2, 0.5)).toBe(300_000);
    expect(nextDelay(9, 0.5)).toBe(300_000);
  });
  it("tests may shorten the interval, never below 2 s", () => {
    expect(basePollMs(() => "3000")).toBe(3000);
    expect(basePollMs(() => "500")).toBe(POLL_MS);
    expect(basePollMs(() => null)).toBe(POLL_MS);
    expect(basePollMs(() => { throw new Error("no storage"); })).toBe(POLL_MS); // prettier-ignore
  });
});

function reading(iso: string, c: number | null, dd = "V"): HfReading {
  return {
    observed_at: iso, age_minutes: 0,
    temp: c === null ? null : { c, f_exact: (18 * c + 320) / 10, f_rounded: Math.floor((18 * c + 325) / 10), f_possible: null, precision: "whole_c", source: "hfmetar", observed_at: iso },
    temp_c: c, temp_precision: c === null ? null : "whole_c", dewpt_c: 5, wind_dir_deg: 180, wind_kt: 8, gust_kt: null,
    altim_inhg: 30.07, vis_mi: 10, precip_in: 0, qc_temp: dd, qc_failed: dd === "Q", qc: null, revision: 0,
    received_at: iso, ingested_at: iso,
  };
} // prettier-ignore

describe("5-minute chart helpers (B3)", () => {
  const end = "2026-11-28T18:00:00Z";
  const times = (from: number, n: number) =>
    Array.from({ length: n }, (_, i) =>
      new Date(Date.parse(end) - (from - i * 5) * 60_000).toISOString(),
    );
  it("leaves a gap when more than 2 × the 5-minute cadence is missing", () => {
    const readings = [...times(60, 6), ...times(25, 6)].map((t) => reading(t, 17)); // 60..35, 25..0 min ago
    const hf: HfSeriesResponse = { generated_at: end, station_id: "KDFW", hours: 6, in_feed: true, source: { source: "", producer: "", attribution: "", last_success_at: null }, readings }; // prettier-ignore
    const p = prepareHf(hf, null, 6);
    expect(HF_GAP_MIN).toBe(10);
    const inner = p.gaps.filter((g) => g.startMs > p.startMs);
    expect(inner).toHaveLength(0); // 35 → 25 is exactly 10 minutes: not a gap
    const hf2 = { ...hf, readings: [...times(60, 5), ...times(25, 6)].map((t) => reading(t, 17)) }; // 40 → 25 = 15 min
    expect(prepareHf(hf2, null, 6).gaps.filter((g) => g.startMs > p.startMs)).toHaveLength(1);
  });
  it("the normal upstream delay at the right edge is not a gap; a late feed is", () => {
    const mk = (minsAgo: number) => {
      const hf: HfSeriesResponse = { generated_at: end, station_id: "KDFW", hours: 6, in_feed: true, source: { source: "", producer: "", attribution: "", last_success_at: null },
        readings: times(60 + minsAgo, 12).map((t) => reading(t, 17)) }; // prettier-ignore
      return prepareHf(hf, null, 6).gaps.filter((g) => g.endMs === Date.parse(end));
    };
    expect(mk(15)).toHaveLength(0); // newest reading 15 min old: just the delay
    expect(mk(40)).toHaveLength(1); // 40 min: the feed is late, shown as a gap
  });
  it("plots the unrounded °F, marks the METARs and says so in the summary", () => {
    const hf: HfSeriesResponse = { generated_at: end, station_id: "KDFW", hours: 6, in_feed: true, source: { source: "", producer: "", attribution: "", last_success_at: null },
      readings: [reading("2026-11-28T17:50:00Z", 17), reading("2026-11-28T17:55:00Z", 30, "Q")] }; // prettier-ignore
    const obs = { generated_at: end, points: [{ observed_at: "2026-11-28T17:53:00Z", temp_c: 17.2, report_type: "METAR" }] } as unknown as ObservedResponse; // prettier-ignore
    const p = prepareHf(hf, obs, 6);
    expect(p.points[0]!.tempF).toBe(62.6);
    expect(p.metar).toEqual([{ t: Date.parse("2026-11-28T17:53:00Z"), tempF: 62.96, observed_at: "2026-11-28T17:53:00Z", report_type: "METAR" }]); // prettier-ignore
    const text = summarizeHf(p, 6, "America/Chicago");
    expect(text).toContain("2 five-minute readings");
    expect(text).toContain("ranged 63–63 °F (62.6–62.6 °F unrounded)"); // the QC-failed 30 °C is left out
    expect(text).toContain("1 reading flagged by MADIS quality control");
    expect(text).toContain("1 hourly METAR reports marked");
  });
  it("computes relative humidity like the API", () => {
    expect(rhFrom(20, 20)).toBe(100);
    expect(rhFrom(20, 10)).toBe(53);
    expect(rhFrom(null, 10)).toBeNull();
  });
});
