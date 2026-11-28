import { describe, expect, it } from "vitest";

import type { MapStation } from "@/lib/premium/types";

import { layout, spread } from "./overlap";
import { BINS, binFor, contrast, STALE_COLOR } from "./scale";
import { accessibleLabel, sortStations, valueFor, visibleFor } from "./values";

describe("colour scale (B5)", () => {
  it("every bin and the delayed grey have ≥ 4.5:1 contrast with the white marker text", () => {
    for (const c of [...BINS.map((b) => b.color), STALE_COLOR]) {
      expect(contrast(c, "#FFFFFF"), c).toBeGreaterThanOrEqual(4.5);
    }
  });
  it("fixed 10 °F bins from below 0 to 100+", () => {
    expect(BINS.map((b) => b.label)).toEqual(["<0", "0s", "10s", "20s", "30s", "40s", "50s", "60s", "70s", "80s", "90s", "100+"]); // prettier-ignore
    expect(binFor(-12).label).toBe("<0");
    expect(binFor(0).label).toBe("0s");
    expect(binFor(59).label).toBe("50s");
    expect(binFor(60).label).toBe("60s");
    expect(binFor(104).label).toBe("100+");
  });
});

describe("overlapping markers (B5)", () => {
  it("a crowd (zoomed far out) becomes one cluster button; small groups are spread", () => {
    const crowd = Array.from({ length: 6 }, (_, i) => ({ id: `S${i}`, x: 100 + i * 8, y: 100 }));
    const pair = [{ id: "P1", x: 400, y: 300 }, { id: "P2", x: 410, y: 300 }];
    const out = layout([...crowd, ...pair]);
    expect(out.clusters).toHaveLength(1);
    expect(out.clusters[0]!.ids).toEqual(["S0", "S1", "S2", "S3", "S4", "S5"]);
    expect(out.clusters[0]!.x).toBe(120);
    expect(out.offsets.has("S0")).toBe(false); // hidden behind the cluster
    expect(out.offsets.get("P1")).not.toEqual([0, 0]); // spread
  }); // prettier-ignore
  it("leaves lone markers alone and spreads close ones at least minDist apart", () => {
    const out = spread([
      { id: "KNYC", x: 500, y: 200 },
      { id: "KLGA", x: 504, y: 201, w: 72 }, // a wide METAR marker
      { id: "KDFW", x: 100, y: 400 },
    ]);
    expect(out.get("KDFW")).toEqual([0, 0]);
    const a = out.get("KNYC")!;
    const b = out.get("KLGA")!;
    // after spreading, their boxes (34 and 72 px wide, 26 px tall) no longer overlap
    const dx = Math.abs(500 + a[0] - (504 + b[0]));
    const dy = Math.abs(200 + a[1] - (201 + b[1]));
    expect(dx >= (34 + 72) / 2 || dy >= 26).toBe(true);
  });
  it("three in a row become a triangle, all reachable", () => {
    const pts = [
      { id: "A", x: 0, y: 0 },
      { id: "B", x: 10, y: 0 },
      { id: "C", x: 20, y: 0 },
    ];
    const out = spread(pts);
    const placed = pts.map((p) => [p.x + out.get(p.id)![0], p.y + out.get(p.id)![1]]);
    for (let i = 0; i < 3; i++)
      for (let j = i + 1; j < 3; j++)
        expect(Math.hypot(placed[i]![0]! - placed[j]![0]!, placed[i]![1]! - placed[j]![1]!)).toBeGreaterThanOrEqual(32);
  }); // prettier-ignore
});

const temp = (c: number, iso: string) => ({ c, f_exact: (18 * c + 320) / 10, f_rounded: Math.floor((18 * c + 325) / 10), f_possible: [62, 63], precision: "whole_c" as const, source: "hfmetar" as const, observed_at: iso }); // prettier-ignore
const at = "2026-11-28T20:50:00Z";
function station(over: Partial<MapStation>): MapStation {
  return {
    station_id: "KDFW", name: "Dallas/Fort Worth", city: "Dallas", state: "TX", tz: "America/Chicago",
    lat: 32.9, lon: -97, venues: ["kalshi", "polymarket"], status: "ok", in_feed: true,
    hf_latest: { observed_at: at, temp: temp(17, at) } as MapStation["hf_latest"],
    hf_so_far: { high: { value_c: 17, precision: "whole_c", observed_at: at, temp: temp(17, at) }, low: null, readings: 1, used: 1, excluded_qc_count: 0, excluded_off_grid_count: 0, missing_temp_count: 0 },
    metar: { latest: null, high_so_far: null, low_so_far: null },
    ...over,
  };
} // prettier-ignore

describe("station values and list (B5)", () => {
  it("the accessible text names the value, unrounded value, time and venues", () => {
    expect(accessibleLabel(station({}), "high")).toBe(
      "KDFW, Dallas/Fort Worth, high so far 63 °F (62.6 °F unrounded) at 2:50 PM, Kalshi and Polymarket",
    );
  });
  it("delayed 5-minute data stays 5-minute, marked stale; no 5-minute data → METAR", () => {
    expect(valueFor(station({ status: "stale" }), "now")).toMatchObject({
      source: "5min",
      stale: true,
    });
    const nyc = station({
      station_id: "KNYC", in_feed: false, hf_latest: null,
      metar: { latest: { temp: { ...temp(8, at), precision: "tenths_c" }, observed_at: at } as MapStation["metar"]["latest"], high_so_far: null, low_so_far: null },
    }); // prettier-ignore
    expect(valueFor(nyc, "now")).toMatchObject({ source: "metar", stale: false });
    expect(accessibleLabel(nyc, "now")).toContain("hourly METAR (not in the 5-minute feed)");
    expect(accessibleLabel(nyc, "high")).toContain("high so far not available");
  });
  it("filters by venue and sorts by value (missing last) or by id", () => {
    const a = station({ station_id: "KAAA", venues: ["robinhood"] });
    const b = station({ station_id: "KBBB", hf_so_far: { ...station({}).hf_so_far, high: null } });
    const c = station({ station_id: "KCCC", hf_so_far: { ...station({}).hf_so_far, high: { value_c: 20, precision: "whole_c", observed_at: at, temp: temp(20, at) } } }); // prettier-ignore
    expect(visibleFor(a, "kalshi")).toBe(false);
    expect(visibleFor(a, "all")).toBe(true);
    expect(sortStations([a, b, c], "high", "value").map((s) => s.station_id)).toEqual([
      "KCCC",
      "KAAA",
      "KBBB",
    ]);
    expect(sortStations([c, b, a], "high", "id").map((s) => s.station_id)).toEqual([
      "KAAA",
      "KBBB",
      "KCCC",
    ]);
  });
});
