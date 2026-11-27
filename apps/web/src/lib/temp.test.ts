import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { cToFExact, fmtC, fmtExactF } from "./temp";
import { cToFDisplay } from "./units";

// The same cases drive packages/core/tests/test_units.py: Python and TypeScript must agree.
const shared = JSON.parse(
  readFileSync(
    fileURLToPath(
      new URL("../../../../packages/core/tests/fixtures/temp_cases.json", import.meta.url),
    ),
    "utf8",
  ),
) as { cases: { c: number; f_exact: number; f_rounded: number }[] };

describe("°C → °F exact and rounded (Python parity)", () => {
  it.each(shared.cases)("$c °C → $f_exact °F → $f_rounded", ({ c, f_exact, f_rounded }) => {
    expect(cToFExact(c)).toBe(f_exact);
    expect(cToFDisplay(c)).toBe(f_rounded);
  });
  it("uses the shared file", () => expect(shared.cases.length).toBeGreaterThan(10));
});

describe("formatting", () => {
  it("exact °F keeps its real digits", () => {
    expect(fmtExactF(62.96)).toBe("62.96");
    expect(fmtExactF(62.6)).toBe("62.6");
    expect(fmtExactF(-4.504)).toBe("-4.504");
  });
  it("°C with its precision", () => {
    expect(fmtC({ c: 17.2, precision: "tenths_c" })).toBe("17.2");
    expect(fmtC({ c: 17, precision: "whole_c" })).toBe("17");
    expect(fmtC({ c: -0.5, precision: "tenths_c" })).toBe("-0.5");
  });
});
