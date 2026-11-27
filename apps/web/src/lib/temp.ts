/**
 * Temperatures with both the exact and the whole-°F value (v2 Phase 9 B9). The API sends a
 * `TempValue` for current temperature, high so far and low so far; these helpers format it.
 * Same arithmetic as packages/core/src/edgefront_core/units.py (shared test cases:
 * packages/core/tests/fixtures/temp_cases.json).
 */

export type TempPrecision = "tenths_c" | "whole_c";
export type TempSource = "metar_tgroup" | "metar_body" | "metar_6h_group" | "hfmetar";

export interface TempValue {
  c: number;
  f_exact: number;
  f_rounded: number;
  precision: TempPrecision;
  source: TempSource;
  observed_at: string;
}

/** °C → °F exactly (no rounding), in integer arithmetic so tenths °C give exact hundredths. */
export function cToFExact(c: number): number {
  const scaled = Math.round(c * 10000); // 1/10000 °C
  const num = scaled * 9 + 32 * 50000; // °F × 50000
  return Math.round((num / 50000) * 10000) / 10000;
}

/** "62.96" / "62.6": the exact °F with the digits it really has (no padding, no rounding). */
export function fmtExactF(f: number): string {
  return String(Math.round(f * 10000) / 10000);
}

/** "17.2" for tenths °C, "17" for whole °C. */
export function fmtC(t: Pick<TempValue, "c" | "precision">): string {
  return t.precision === "tenths_c" ? t.c.toFixed(1) : String(Math.round(t.c));
}

/** A whole-°C value is only good to ±0.5 °C, i.e. ±0.9 °F. */
export const WHOLE_C_UNCERTAINTY_F = 0.9;
