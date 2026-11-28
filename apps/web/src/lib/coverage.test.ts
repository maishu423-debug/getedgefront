import { describe, expect, it } from "vitest";

import registry from "@/generated/stations.json";

import { COVERAGE, coverage, inFiveMinuteFeed, shortName } from "./coverage";

describe("5-minute coverage, counted from the registry", () => {
  it("matches data/stations.yaml: KNYC and KBKF are outside the feed", () => {
    const outside = registry.stations.filter((s) => s.fiveMinute === false).map((s) => s.id);
    expect(outside.sort()).toEqual(["KBKF", "KNYC"]);
    expect(COVERAGE.total).toBe(registry.stations.length);
    expect(COVERAGE.inFeed).toBe(registry.stations.length - 2);
    expect(COVERAGE.sentence).toBe(
      `5-minute data for ${registry.stations.length - 2} of ${registry.stations.length} stations (not KNYC Central Park or KBKF Buckley)`,
    );
    expect(inFiveMinuteFeed("KNYC")).toBe(false);
    expect(inFiveMinuteFeed("KDFW")).toBe(true);
  });
  it("follows the data, not a constant", () => {
    const all = coverage([
      { id: "KAAA", name: "A", fiveMinute: true },
      { id: "KBBB", name: "B", fiveMinute: true },
    ]);
    expect(all.sentence).toBe("5-minute data for all 2 stations");
    const three = coverage([
      { id: "KAAA", name: "Town · North", fiveMinute: false },
      { id: "KBBB", name: "B", fiveMinute: false },
      { id: "KCCC", name: "C", fiveMinute: false },
      { id: "KDDD", name: "D" },
    ]);
    expect(three.sentence).toBe(
      "5-minute data for 1 of 4 stations (not KAAA North, KBBB B, KCCC C)",
    );
    expect(shortName("New York · Central Park")).toBe("Central Park");
  });
});
