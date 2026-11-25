import { describe, expect, it } from "vitest";

import type { ModelSeries, ModelsResponse } from "@/lib/types";

import { buildModelOption } from "./ModelGuidance";
import {
  fmtPointValue,
  readState,
  runLabel,
  runLine,
  summarize,
  toSeriesData,
  tooltipLines,
  writeState,
} from "./models";

const z = (d: number, h: number, mi = 0) => new Date(Date.UTC(2026, 10, d, h, mi)).toISOString();
const pt = (iso: string, value: number | null, category: string | null = null) => ({
  valid_time: iso,
  value,
  category,
  is_computed: false,
});

function series(over: Partial<ModelSeries>): ModelSeries {
  return {
    id: "nbm", label: "NBM", group: "statistical", producer: "NWS National Blend of Models",
    colour_token: "model-nbm", licence: null, available: true, reason: null, reason_code: null,
    kind: "continuous", native_unit: "degF", native_step_hours: [1, 3],
    run: {
      cycle_time: z(25, 13), issuer: null, available_at: z(25, 14, 50), fetched_at: z(25, 14, 50),
      status: "complete", steps_expected: 2, steps_fetched: 2, source_url: null, stale: false,
    },
    grid: null, points: [], ...over,
  }; // prettier-ignore
}

function response(models: ModelSeries[]): ModelsResponse {
  return {
    generated_at: z(25, 15), station_id: "KDFW", station_name: "Dallas/Fort Worth", variable: "temp",
    unit: "degF", now: z(25, 15),
    window: { span: "today", start: z(25, 6), end: z(26, 6), start_local: "2026-11-25T00:00:00-06:00",
      end_local: "2026-11-26T00:00:00-06:00", climate_date: "2026-11-25", basis: "LST" },
    observed: { source: { source: "aviationweather", producer: "NOAA AWC", last_success_at: null },
      points: [pt(z(25, 13, 53), 35), pt(z(25, 14, 53), 38)] },
    models,
  }; // prettier-ignore
}

describe("URL state", () => {
  it("round-trips variable, span and hidden chips and keeps other params", () => {
    const st = readState("?mvar=wind&mspan=48h&mhide=pfm,gfs,pfm&x=1");
    expect(st).toEqual({ variable: "wind", span: "48h", hidden: ["gfs", "pfm"] });
    expect(writeState("?x=1", st)).toBe("?x=1&mvar=wind&mspan=48h&mhide=gfs%2Cpfm");
    expect(readState(writeState("", st))).toEqual(st);
  });
  it("falls back to defaults on junk and writes nothing for the default view", () => {
    expect(readState("?mvar=pressure&mspan=week")).toEqual({
      variable: "temp",
      span: "today",
      hidden: [],
    });
    expect(writeState("", { variable: "temp", span: "today", hidden: [] })).toBe("");
  });
});

describe("series mapping", () => {
  it("keeps real valid times and breaks only gaps > 2x the longest native step", () => {
    const pts = [pt(z(25, 14), 36), pt(z(25, 15), 39), pt(z(25, 18), 47), pt(z(26, 3), 40)];
    const d = toSeriesData(pts, [1, 3]); // max gap 6 h
    expect(d.map(([t]) => new Date(t).toISOString())).toEqual([
      z(25, 14), z(25, 15), z(25, 18), z(25, 18, 1), z(26, 3),
    ]); // prettier-ignore
    expect(d[3]![1]).toBeNull(); // 9 h gap → line break, no invented point value
    expect(d.filter(([, v]) => v !== null)).toHaveLength(4);
  });
  it("categorical points keep their category and midpoint", () => {
    expect(fmtPointValue(pt(z(25, 12), 100, "OV"), "pct")).toBe("OV (overcast)");
    expect(fmtPointValue({ ...pt(z(25, 12), 54), is_computed: true }, "pct")).toBe(
      "54 % (computed)",
    );
  });
});

describe("labels", () => {
  it("run label, run line, stale and partial", () => {
    expect(runLabel(z(25, 13, 30))).toBe("1330Z Nov 25");
    const m = series({
      run: { ...series({}).run!, status: "partial", steps_fetched: 30, steps_expected: 55, stale: true },
      grid: { lat: 32.9, lon: -97, distance_km: 7.36, height_m: 172.7, point_name: null },
      group: "global",
    }); // prettier-ignore
    const line = runLine(m, Date.parse(z(25, 20)));
    expect(line).toContain("run 13Z Nov 25");
    expect(line).toContain("partial: 30 of 55 steps");
    expect(line).toContain("grid point 7.4 km away, model height 173 m");
    expect(line).toContain("stale: newest run received 5 h ago");
    expect(runLine(series({ available: false, reason: "no rh", run: null }), null)).toBe("no rh");
  });
  it("tooltip carries model, run, received, valid Z + local, value, native unit, distance", () => {
    const m = series({
      grid: { lat: 32.91, lon: -97.03, distance_km: 1.59, height_m: 171, point_name: "DFW" },
    });
    const lines = tooltipLines(m, pt(z(25, 18), 47), "degF", "America/Chicago");
    expect(lines).toEqual([
      "NBM · NWS National Blend of Models",
      "Run 13Z Nov 25 · received 14:50Z",
      expect.stringMatching(/^Valid 18:00Z \(12:00 (PM )?CST\)$|^Valid 18:00Z \(/),
      "Value 47°F",
      "Native unit °F",
      "Point 1.6 km from the station",
    ]);
  });
});

describe("summary and chart option", () => {
  const data = response([
    series({ points: [pt(z(25, 14), 36), pt(z(25, 20), 51)] }),
    series({ id: "pfm", label: "PFM", group: "nws", colour_token: "model-pfm", available: false,
      reason: "Not available for this station (no PFM point)", reason_code: "no_station", run: null }),
  ]); // prettier-ignore
  it("summarizes visible models, observed and what is not shown", () => {
    const s = summarize(data, new Set(["nbm"]), "America/Chicago");
    expect(s).toContain("climate day 2026-11-25 (local standard time)");
    expect(s).toContain("NBM 13Z Nov 25: 36°F–51°F");
    expect(s).toContain("observed so far 35°F–38°F");
    expect(s).toContain("Not shown: PFM (Not available for this station (no PFM point))");
  });
  it("builds one line per visible model plus observed, Now marker and past shading", () => {
    const opt = buildModelOption(data, new Set(["nbm"]), "America/Chicago") as {
      series: { name: string; symbol?: string; lineStyle?: { width: number }; markLine?: { data: unknown[] }; markArea?: { data: unknown[] } }[];
    }; // prettier-ignore
    const names = opt.series.map((x) => x.name);
    expect(names).toEqual(["_frame", "NBM", "Observed (METAR)"]);
    expect(opt.series[1]!.symbol).toBe("roundRect");
    expect(opt.series[2]!.lineStyle!.width).toBe(3);
    expect(opt.series[0]!.markLine!.data).toHaveLength(1);
    expect(opt.series[0]!.markArea!.data).toHaveLength(1);
    const hidden = buildModelOption(data, new Set(), "America/Chicago") as {
      series: { name: string }[];
    };
    expect(hidden.series.map((x) => x.name)).toEqual(["_frame", "Observed (METAR)"]);
  });
});

describe("PFM categories", () => {
  it("tooltip value shows the PFM code and its sky-cover range", () => {
    expect(
      fmtPointValue({ ...pt(z(25, 15), 59.5, "B1"), category_range: "> 50% and ≤ 69%" }, "pct"),
    ).toBe("B1 (broken (B1), sky cover > 50% and ≤ 69%)");
  });
});
