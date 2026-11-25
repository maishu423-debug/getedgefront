import { describe, expect, it } from "vitest";

import { climateDayBounds, formatCountdown, standardOffsetMinutes } from "./climate";
import { breakAtGaps, findGaps } from "./gaps";
import { searchStations } from "./search";
import { formatLocalTime, formatZulu, hhmmTo12h, relativeAge, tzAbbrev } from "./time";
import { uiStateFor } from "./uiState";
import { cToFDisplay, fmtMetarWind, fmtMphWind, fmtPrecip } from "./units";

const utc = (s: string) => Date.parse(s);

describe("cToFDisplay — same cases as test_units.py", () => {
  it.each([
    [20.0, 68],
    [-4.4, 24],
    [0.0, 32],
    [-17.5, 1], // 0.5 → half away from zero → 1
    [-18.5, -1], // -1.3
    [-20.25, -4], // -4.45
    [-20.28, -5], // -4.504
    [37.5, 100], // 99.5
    [8.3, 47],
  ])("%s °C → %s °F", (c, f) => expect(cToFDisplay(c)).toBe(f));
  it("missing stays missing", () => {
    expect(cToFDisplay(null)).toBeNull();
    expect(cToFDisplay(undefined)).toBeNull();
    expect(cToFDisplay(Number.NaN)).toBeNull();
  });
  it("never returns -0", () => expect(Object.is(cToFDisplay(-17.78), -0)).toBe(false));
});

describe("climate day (LST)", () => {
  it("standard offsets", () => {
    expect(standardOffsetMinutes("America/New_York", utc("2026-07-15T12:00:00Z"))).toBe(-300);
    expect(standardOffsetMinutes("America/Phoenix", utc("2026-07-15T12:00:00Z"))).toBe(-420);
    expect(standardOffsetMinutes("America/Kentucky/Louisville", utc("2026-01-15T12:00:00Z"))).toBe(
      -300,
    );
  });
  it("winter Chicago: 06Z → 06Z", () => {
    const b = climateDayBounds(utc("2026-11-24T17:30:00Z"), "America/Chicago");
    expect(b.date).toBe("2026-11-24");
    expect(new Date(b.startMs).toISOString()).toBe("2026-11-24T06:00:00.000Z");
    expect(new Date(b.endMs).toISOString()).toBe("2026-11-25T06:00:00.000Z");
  });
  it("during DST the day ends at 1:00 AM local clock time", () => {
    const b = climateDayBounds(utc("2026-07-15T20:00:00Z"), "America/New_York");
    expect(new Date(b.endMs).toISOString()).toBe("2026-07-16T05:00:00.000Z");
    expect(formatLocalTime(new Date(b.endMs).toISOString(), "America/New_York")).toBe("1:00 AM");
  });
  it("00:30 EDT still belongs to the previous climate day", () => {
    expect(climateDayBounds(utc("2026-07-15T04:30:00Z"), "America/New_York").date).toBe(
      "2026-07-14",
    );
  });
  it("DST change day is still 24 h (spring forward)", () => {
    const b = climateDayBounds(utc("2026-03-08T15:00:00Z"), "America/New_York");
    expect(b.date).toBe("2026-03-08");
    expect(b.endMs - b.startMs).toBe(24 * 3600 * 1000);
  });
  it("countdown", () => {
    const end = utc("2026-11-25T06:00:00Z");
    expect(formatCountdown(end, utc("2026-11-24T22:05:00Z"))).toBe("7 h 55 m");
    expect(formatCountdown(end, utc("2026-11-25T05:45:00Z"))).toBe("15 m");
    expect(formatCountdown(end, utc("2026-11-25T07:00:00Z"))).toBe("0 m");
  });
});

describe("time formatting", () => {
  it("zulu", () => {
    expect(formatZulu("2026-11-24T21:05:12Z")).toBe("21:05Z");
    expect(formatZulu(null)).toBe("—");
    expect(formatZulu("bad")).toBe("—");
  });
  it("local + abbreviation from the station tz", () => {
    expect(formatLocalTime("2026-11-24T20:51:00Z", "America/Chicago")).toBe("2:51 PM");
    expect(tzAbbrev("2026-11-24T20:51:00Z", "America/Chicago")).toBe("CST");
    expect(tzAbbrev("2026-07-24T20:51:00Z", "America/Chicago")).toBe("CDT");
  });
  it("relative age", () => {
    const now = utc("2026-11-24T21:05:00Z");
    expect(relativeAge("2026-11-24T21:04:40Z", now)).toBe("just now");
    expect(relativeAge("2026-11-24T20:53:00Z", now)).toBe("12 min ago");
    expect(relativeAge("2026-11-24T19:00:00Z", now)).toBe("2 h 5 min ago");
    expect(relativeAge("2026-11-24T19:05:00Z", now)).toBe("2 h ago");
    expect(relativeAge("2026-11-20T21:05:00Z", now)).toBe("4 d ago");
    expect(relativeAge(null, now)).toBe("—");
  });
  it("hh:mm → 12 h", () => {
    expect(hhmmTo12h("14:07")).toBe("2:07 PM");
    expect(hhmmTo12h("00:05")).toBe("12:05 AM");
    expect(hhmmTo12h("12:00")).toBe("12:00 PM");
    expect(hhmmTo12h("24:00")).toBe("12:00 AM");
    expect(hhmmTo12h(null)).toBe("—");
  });
});

describe("search", () => {
  const S = [
    {
      id: "KNYC",
      name: "New York · Central Park",
      city: "New York",
      state: "NY",
      aliases: ["NYC", "Manhattan"],
    },
    {
      id: "KLGA",
      name: "New York · LaGuardia",
      city: "New York",
      state: "NY",
      aliases: ["NYC", "LGA"],
    },
    {
      id: "KDCA",
      name: "Washington DC · Reagan National",
      city: "Washington",
      state: "DC",
      aliases: ["DC"],
    },
    {
      id: "KLAX",
      name: "Los Angeles Intl",
      city: "Los Angeles",
      state: "CA",
      aliases: ["LA", "LAX"],
    },
    {
      id: "KMDW",
      name: "Chicago · Midway",
      city: "Chicago",
      state: "IL",
      aliases: ["Chi", "Midway"],
    },
    { id: "KORD", name: "Chicago · O'Hare", city: "Chicago", state: "IL", aliases: ["O'Hare"] },
  ];
  const ids = (q: string) => searchStations(S, q).map((s) => s.id);
  it("codes with and without K, any case", () => {
    expect(ids("KMDW")).toEqual(["KMDW"]);
    expect(ids("mdw")[0]).toBe("KMDW");
  });
  it("cities and names", () => {
    expect(ids("chicago")).toEqual(["KMDW", "KORD"]);
    expect(ids("los ang")).toEqual(["KLAX"]);
    expect(ids("o hare")[0]).toBe("KORD");
  });
  it("aliases", () => {
    expect(ids("NYC")).toEqual(["KNYC", "KLGA"]); // exact code (NYC) first, then alias
    expect(ids("dc")[0]).toBe("KDCA");
    expect(ids("LA")[0]).toBe("KLAX");
  });
  it("no match / empty", () => {
    expect(ids("zzzz")).toEqual([]);
    expect(ids("  ")).toEqual([]);
  });
});

describe("status → UI state", () => {
  it.each([
    [{ notFound: true }, "not_found"],
    [{ requestFailed: true }, "upstream_down"],
    [{ status: "none_available" as const }, "not_available"],
    [{ status: "not_available" as const }, "not_available"],
    [{ status: "no_data" as const }, "no_data"],
    [{ status: "not_issued_yet" as const }, "no_data"],
    [{ status: "stale" as const }, "stale"],
    [{ status: "ok" as const, sourceHealthy: false, hasData: true }, "upstream_down"],
    [{ status: "ok" as const, sourceHealthy: false, hasData: false }, "no_data"],
    [{ status: "ok" as const, sourceHealthy: true }, "ok"],
  ])("%o → %s", (input, out) => expect(uiStateFor(input)).toBe(out));
});

describe("units display", () => {
  it("METAR wind is knots, DSM/CLI wind is mph", () => {
    expect(fmtMetarWind(330, false, 16, 23)).toBe("330° 16 kt G23");
    expect(fmtMetarWind(null, true, 3, null)).toBe("VRB 3 kt");
    expect(fmtMetarWind(0, false, 0, null)).toBe("Calm");
    expect(fmtMetarWind(null, false, null, null)).toBe("—");
    expect(fmtMphWind(300, 32)).toBe("32 mph from WNW (300°)");
  });
  it("precip", () => {
    expect(fmtPrecip(0.78, false)).toBe("0.78 in");
    expect(fmtPrecip(null, true)).toBe("Trace");
    expect(fmtPrecip(null, false)).toBe("—");
  });
});

describe("gaps", () => {
  const t0 = utc("2026-11-24T00:00:00Z");
  const h = (n: number) => t0 + n * 3600_000;
  it("finds gaps over 90 min incl. window edges", () => {
    const g = findGaps([h(1), h(2), h(5)], h(0), h(6));
    expect(g.map((x) => x.minutes)).toEqual([180]);
    expect(findGaps([], h(0), h(6))[0]!.minutes).toBe(360);
  });
  it("breaks lines across gaps", () => {
    const pts = [
      { t: h(1), v: 1 },
      { t: h(2), v: 2 },
      { t: h(5), v: 5 },
    ];
    expect(breakAtGaps(pts).map((p) => p[1])).toEqual([1, 2, null, 5]);
  });
});
