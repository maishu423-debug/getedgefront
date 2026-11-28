import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  conversionTooltip,
  fmtC,
  fmtFExact,
  fToC,
  fToC10,
  spokenTemp,
  tempFromC,
  unroundedLine,
  type TempValue,
} from "./temp";
import { cToFDisplay } from "./units";

// The same vectors drive packages/core/tests/test_units.py: Python and TypeScript must agree.
type Case = {
  c: number;
  precision: "tenths_c" | "whole_c";
  f_exact: number;
  f_rounded: number;
  f_possible: number[];
};
const shared = JSON.parse(
  readFileSync(
    fileURLToPath(
      new URL("../../../../packages/core/tests/fixtures/temp_cases.json", import.meta.url),
    ),
    "utf8",
  ),
) as { cases: Case[] };

describe("shared temperature vectors (Python parity)", () => {
  it.each(shared.cases)("$c C ($precision)", (k) => {
    const t = tempFromC(k.c, k.precision);
    expect(t.f_exact).toBe(k.f_exact);
    expect(t.f_rounded).toBe(k.f_rounded);
    expect(t.f_possible).toEqual(k.f_possible);
    expect(cToFDisplay(k.c)).toBe(k.f_rounded);
  });
  it("uses the shared file", () => expect(shared.cases.length).toBeGreaterThan(15));
});

describe("NWS rounding (FMH-1 2.6.3), not Python round() or half away from zero", () => {
  it("2.5 C = 36.5 F -> 37, -22.5 C = -8.5 F -> -8", () => {
    expect(cToFDisplay(2.5)).toBe(37);
    expect(cToFDisplay(-22.5)).toBe(-8);
  });
  it("F -> C conversions", () => {
    expect([fToC10(63), fToC10(64), fToC10(0)]).toEqual([172, 178, -178]);
    expect([fToC(62), fToC(63), fToC(30), fToC(31)]).toEqual([17, 17, -1, -1]);
  });
  it("stations measuring in C have no possible F readings", () =>
    expect(tempFromC(-2, "tenths_c", "C").f_possible).toBeNull());
});

const tv = (c: number, precision: "tenths_c" | "whole_c", native: "F" | "C" = "F"): TempValue => ({
  ...tempFromC(c, precision, native),
  source: precision === "tenths_c" ? "metar_tgroup" : "metar_body",
  observed_at: "2026-11-27T20:53:00Z",
});

describe("UI strings", () => {
  it("tenths C", () => expect(unroundedLine(tv(17.2, "tenths_c"))).toBe("62.96 °F unrounded · 17.2 °C"));
  it("whole C with two possible readings", () =>
    expect(unroundedLine(tv(17, "whole_c"))).toBe("62.6 °F unrounded · 17 °C · reading 62–63 °F"));
  it("whole C with one possible reading", () =>
    expect(unroundedLine(tv(0, "whole_c"))).toBe("32.0 °F unrounded · 0 °C · reading 32 °F"));
  it("negative and exact two decimals", () => {
    expect(unroundedLine(tv(-20, "tenths_c"))).toBe("-4.00 °F unrounded · -20.0 °C");
    expect(fmtFExact(tv(-17.8, "tenths_c"))).toBe("-0.04");
    expect(fmtC({ c: 17, precision: "whole_c" })).toBe("17");
  });
  it("C station: no reading part", () =>
    expect(unroundedLine(tv(-1, "whole_c", "C"))).toBe("30.2 °F unrounded · -1 °C"));
  it("spoken / tooltip text", () => {
    expect(spokenTemp("High so far", tv(17.2, "tenths_c"), "2:53 PM")).toBe("High so far 63 °F (62.96 °F unrounded), at 2:53 PM");
    expect(spokenTemp("Low so far", tv(17, "whole_c"))).toBe("Low so far 63 °F (62.6 °F unrounded; station reading 62–63 °F)");
  });
}); // prettier-ignore

describe("conversion tooltip (5-minute table)", () => {
  it("whole °C: converted, rounded and the station's possible readings", () => {
    expect(conversionTooltip(tempFromC(17, "whole_c"))).toBe(
      "Converted from 17 °C → 62.6 °F, rounds to 63 °F. The station's own reading was 62 or 63 °F.",
    );
    expect(conversionTooltip(tempFromC(20, "whole_c"))).toBe(
      "Converted from 20 °C → 68.0 °F, rounds to 68 °F. The station's own reading was 68 °F.",
    );
  });
  it("tenths °C, and stations measuring in °C (no possible readings)", () => {
    expect(conversionTooltip(tempFromC(17.2, "tenths_c"))).toBe(
      "Converted from 17.2 °C → 62.96 °F, rounds to 63 °F. The station's own reading was 63 °F.",
    );
    expect(conversionTooltip(tempFromC(17, "whole_c", "C"))).toBe(
      "Converted from 17 °C → 62.6 °F, rounds to 63 °F.",
    );
  });
});
