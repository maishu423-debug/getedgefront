/**
 * °C → whole °F, rounded half away from zero — the same rule as the API
 * (packages/core/src/edgefront_core/units.py `c_to_f_display`). Integer arithmetic, so there
 * is no floating-point drift at .5 boundaries. Missing stays missing (never 0).
 */
export function cToFDisplay(c: number | null | undefined): number | null {
  if (c === null || c === undefined || !Number.isFinite(c)) return null;
  // Work in 1/10000 °C so values like -20.25 are exact.
  const scaled = Math.round(c * 10000);
  // F = C*9/5 + 32  →  numerator / 50000  (all integers)
  const num = scaled * 9 + 32 * 50000;
  const den = 50000;
  const q = Math.abs(num);
  const rounded = Math.floor((2 * q + den) / (2 * den)); // half up on |x|
  const out = num < 0 ? -rounded : rounded;
  return out === 0 ? 0 : out; // never "-0"
}

export function fmtTempF(f: number | null | undefined): string {
  return f === null || f === undefined ? "—" : `${f}°`;
}

const COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
  "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]; // prettier-ignore

export function compassPoint(deg: number | null | undefined): string | null {
  if (deg === null || deg === undefined) return null;
  return COMPASS[Math.round((((deg % 360) + 360) % 360) / 22.5) % 16] ?? null;
}

/** METAR wind, knots: "330° 16 kt G23", "VRB 3 kt", "Calm", "—". */
export function fmtMetarWind(
  dir: number | null,
  vrb: boolean,
  kt: number | null,
  gust: number | null,
): string {
  if (kt === null) return "—";
  if (kt === 0 && !gust) return "Calm";
  const d = vrb ? "VRB" : dir === null ? "—" : `${String(dir).padStart(3, "0")}°`;
  return `${d} ${kt} kt${gust ? ` G${gust}` : ""}`;
}

/** DSM/CLI wind, mph (labelled — never mixed with METAR knots). */
export function fmtMphWind(dir: number | null, mph: number | null): string {
  if (mph === null) return "—";
  return `${mph} mph${dir !== null ? ` from ${compassPoint(dir)} (${dir}°)` : ""}`;
}

export function fmtPrecip(inches: number | null, trace: boolean): string {
  if (trace) return "Trace";
  if (inches === null) return "—";
  return `${inches.toFixed(2)} in`;
}

export const COVER_RANK: Record<string, number> = {
  CLR: 0, SKC: 0, FEW: 1, SCT: 2, BKN: 3, OVC: 4, VV: 5,
}; // prettier-ignore

export function skyText(layers: { cover: string; base_ft: number | null }[]): string {
  if (!layers.length) return "—";
  return layers
    .map((l) =>
      l.cover === "CLR" || l.cover === "SKC"
        ? "Clear below 12,000 ft"
        : `${{ FEW: "Few", SCT: "Scattered", BKN: "Broken", OVC: "Overcast", VV: "Vertical vis." }[l.cover] ?? l.cover}${
            l.base_ft !== null ? ` ${l.base_ft.toLocaleString("en-US")} ft` : ""
          }`,
    )
    .join(", ");
}
