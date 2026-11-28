/**
 * Marker colours for the live map (v2 Phase 10 B5): fixed 10 °F bins for every season, from
 * below 0 °F to 100 °F and above. The number is always printed on the marker in white, so each
 * colour is checked for a contrast ratio of at least 4.5:1 against white (WCAG AA, normal text;
 * unit test in map.test.ts). Colour is never the only cue.
 */
export interface Bin {
  label: string;
  /** lower bound, °F (inclusive); -Infinity for the first bin */
  from: number;
  color: string;
}

export const BINS: Bin[] = [
  { label: "<0", from: -Infinity, color: "#4B3C8E" },
  { label: "0s", from: 0, color: "#3A4BA0" },
  { label: "10s", from: 10, color: "#2A5BA8" },
  { label: "20s", from: 20, color: "#1F64A0" },
  { label: "30s", from: 30, color: "#1D6E93" },
  { label: "40s", from: 40, color: "#0E717A" },
  { label: "50s", from: 50, color: "#0A6E69" },
  { label: "60s", from: 60, color: "#476A12" },
  { label: "70s", from: 70, color: "#8A5A00" },
  { label: "80s", from: 80, color: "#A84A05" },
  { label: "90s", from: 90, color: "#B23A14" },
  { label: "100+", from: 100, color: "#9E1B2B" },
];

/** Delayed 5-minute data: grey, whatever the value. */
export const STALE_COLOR = "#5E6866";

export function binFor(f: number): Bin {
  let out = BINS[0]!;
  for (const b of BINS) if (f >= b.from) out = b;
  return out;
}

/** WCAG relative luminance and contrast ratio. */
export function luminance(hex: string): number {
  const h = hex.replace("#", "");
  const [r, g, b] = [0, 2, 4].map((i) => {
    const c = parseInt(h.slice(i, i + 2), 16) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi! + 0.05) / (lo! + 0.05);
}
