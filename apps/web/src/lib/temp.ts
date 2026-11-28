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
  /** Whole-°F readings an ASOS station could have made (null: station measures in °C). */
  f_possible: number[] | null;
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

const floorDiv = (a: number, b: number) => Math.floor(a / b); // exact for these integer sizes

/** Whole °F → tenths °C, nearest (ASOS; an exact .5 tie can't occur for a whole °F). */
export const fToC10 = (f: number) => floorDiv(100 * (f - 32) + 9, 18);
/** Whole °F → whole °C, nearest. */
export const fToC = (f: number) => floorDiv(10 * (f - 32) + 9, 18);

/**
 * The same integer maths as the API (owner spec B9), for tests and client-side use:
 *   tenths: f_x100 = 18*c10 + 3200 → f_exact = f_x100/100, f_rounded = floor((f_x100+50)/100)
 *   whole:  f_x10  = 18*c   + 320  → f_exact = f_x10/10,   f_rounded = floor((f_x10+5)/10)
 */
export function tempFromC(
  c: number,
  precision: TempPrecision,
  nativeUnit: "F" | "C" = "F",
): Pick<TempValue, "c" | "f_exact" | "f_rounded" | "f_possible" | "precision"> {
  if (precision === "tenths_c") {
    const c10 = Math.round(c * 10);
    const fx100 = 18 * c10 + 3200;
    const fRounded = floorDiv(fx100 + 50, 100);
    const possible = [-2, -1, 0, 1, 2].map((d) => fRounded + d).filter((f) => fToC10(f) === c10);
    return { c, f_exact: fx100 / 100, f_rounded: fRounded, f_possible: nativeUnit === "F" ? possible : null, precision };
  }
  const cw = Math.round(c);
  const fx10 = 18 * cw + 320;
  const fRounded = floorDiv(fx10 + 5, 10);
  const possible = [-2, -1, 0, 1, 2].map((d) => fRounded + d).filter((f) => fToC(f) === cw);
  return { c, f_exact: fx10 / 10, f_rounded: fRounded, f_possible: nativeUnit === "F" ? possible : null, precision };
} // prettier-ignore

/** "62.96" (tenths °C → exactly 2 decimals) or "62.6" (whole °C → 1 decimal). */
export function fmtFExact(t: Pick<TempValue, "f_exact" | "precision">): string {
  return t.f_exact.toFixed(t.precision === "tenths_c" ? 2 : 1);
}

/** "62–63 °F" / "32 °F": the possible station readings; "" when there are none to give. */
export function fmtPossible(t: Pick<TempValue, "f_possible">): string {
  const p = t.f_possible ?? [];
  if (!p.length) return "";
  return p.length === 1 ? `${p[0]} °F` : `${p[0]}–${p[p.length - 1]} °F`;
}

/**
 * The small line under a big rounded number, always shown (owner B9):
 *   tenths °C: "62.96 °F unrounded · 17.2 °C"
 *   whole °C:  "62.6 °F unrounded · 17 °C · reading 62–63 °F"
 */
export function unroundedLine(t: TempValue): string {
  const base = `${fmtFExact(t)} °F unrounded · ${fmtC(t)} °C`;
  const reading = t.precision === "whole_c" ? fmtPossible(t) : "";
  return reading ? `${base} · reading ${reading}` : base;
}

/** Accessible / tooltip text: "High so far 63 °F (62.96 °F unrounded), at 2:53 PM". */
export function spokenTemp(label: string, t: TempValue, at?: string): string {
  const possible = fmtPossible(t);
  const reading = t.precision === "whole_c" && possible ? `; station reading ${possible}` : "";
  return `${label} ${t.f_rounded} °F (${fmtFExact(t)} °F unrounded${reading})${at ? `, at ${at}` : ""}`;
}

/**
 * Tooltip / accessible text for a converted temperature (v2 Phase 10b, 5-minute table):
 *   "Converted from 17 °C → 62.6 °F, rounds to 63 °F. The station's own reading was 62 or 63 °F."
 * The possible readings are only known for stations that measure in °F (f_possible).
 */
export function conversionTooltip(t: Pick<TempValue, "c" | "f_exact" | "f_rounded" | "f_possible" | "precision">): string {
  const base = `Converted from ${fmtC(t)} °C → ${fmtFExact(t)} °F, rounds to ${t.f_rounded} °F.`;
  const p = t.f_possible ?? [];
  if (!p.length) return base;
  const list = p.length === 1 ? `${p[0]}` : `${p.slice(0, -1).join(", ")} or ${p[p.length - 1]}`;
  return `${base} The station's own reading was ${list} °F.`;
} // prettier-ignore

/** A whole-°C value is only good to ±0.5 °C, i.e. ±0.9 °F. */
export const WHOLE_C_UNCERTAINTY_F = 0.9;
