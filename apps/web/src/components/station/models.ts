/** Pure helpers for the model guidance section: URL state, series mapping, labels, summary. */

import { formatLocalTime, formatZulu } from "@/lib/time";
import type { ModelPoint, ModelSeries, ModelSpan, ModelsResponse, ModelVariable } from "@/lib/types";

export const VARIABLES: { key: ModelVariable; label: string; long: string }[] = [
  { key: "temp", label: "Temp", long: "temperature" },
  { key: "dewpt", label: "Dew pt", long: "dew point" },
  { key: "wind", label: "Wind", long: "wind speed" },
  { key: "cloud", label: "Cloud", long: "cloud cover" },
  { key: "rh", label: "RH", long: "relative humidity" },
];
export const SPANS: { key: ModelSpan; label: string }[] = [
  { key: "today", label: "Today" },
  { key: "48h", label: "48 h" },
];
export const GROUPS: { key: ModelSeries["group"]; label: string }[] = [
  { key: "global", label: "Global" },
  { key: "ai", label: "AI" },
  { key: "statistical", label: "Statistical" },
  { key: "nws", label: "NWS" },
];

/** Canvas can't read CSS tokens directly; the same values as `--color-model-*` in globals.css. */
export const MODEL_COLOR: Record<string, string> = {
  "model-ifs": "#1F5FA8",
  "model-gfs": "#C24E12",
  "model-aifs": "#B4235A",
  "model-gfsmos": "#7D6A00",
  "model-nbm": "#0A6E69",
  "model-lamp": "#3F8F3A",
  "model-pfm": "#6B4FA0",
};
/** A distinct marker per model, so lines are told apart without colour too. */
export const MODEL_SYMBOL: Record<string, string> = {
  ifs: "circle",
  gfs: "rect",
  aifs: "triangle",
  gfs_mos: "diamond",
  nbm: "roundRect",
  lamp: "pin",
  pfm: "arrow",
};
export const OBSERVED_COLOR = "#101A1C";

export const CATEGORY_LABEL: Record<string, string> = {
  CL: "clear", FW: "few", SC: "scattered", BK: "broken", OV: "overcast",
  B1: "broken (B1)", B2: "broken (B2)",
  CLR: "clear", SKC: "clear", FEW: "few", SCT: "scattered", BKN: "broken", OVC: "overcast",
  VV: "sky obscured",
}; // prettier-ignore

// ---------------------------------------------------------------- URL state

export interface ModelUiState {
  variable: ModelVariable;
  span: ModelSpan;
  hidden: string[]; // model ids switched off
}

export const DEFAULT_STATE: ModelUiState = { variable: "temp", span: "today", hidden: [] };
const VAR_KEYS = new Set(VARIABLES.map((v) => v.key));

export function readState(search: string): ModelUiState {
  const q = new URLSearchParams(search);
  const v = q.get("mvar");
  const s = q.get("mspan");
  const hide = (q.get("mhide") ?? "")
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);
  return {
    variable: v && VAR_KEYS.has(v as ModelVariable) ? (v as ModelVariable) : "temp",
    span: s === "48h" ? "48h" : "today",
    hidden: [...new Set(hide)].sort(),
  };
}

/** The page's query string with the model state applied (other params kept). */
export function writeState(search: string, st: ModelUiState): string {
  const q = new URLSearchParams(search);
  q.delete("mvar");
  q.delete("mspan");
  q.delete("mhide");
  if (st.variable !== "temp") q.set("mvar", st.variable);
  if (st.span !== "today") q.set("mspan", st.span);
  if (st.hidden.length) q.set("mhide", [...st.hidden].sort().join(","));
  const s = q.toString();
  return s ? `?${s}` : "";
}

// ---------------------------------------------------------------- series

/** [t, value] pairs with a null inserted where the gap exceeds 2x the product's longest native
 * step, so no line is drawn across missing valid times. Points keep their real valid times. */
export function toSeriesData(
  points: ModelPoint[],
  nativeStepHours: number[],
): [number, number | null][] {
  const maxGap = 2 * Math.max(1, ...nativeStepHours) * 3600_000;
  const out: [number, number | null][] = [];
  let prev: number | null = null;
  for (const p of points) {
    const t = Date.parse(p.valid_time);
    if (prev !== null && t - prev > maxGap) out.push([prev + 60_000, null]);
    out.push([t, p.value]);
    prev = t;
  }
  return out;
}

/** Observed METAR line: breaks across gaps longer than 90 min (the observed-chart rule). */
export function observedData(points: ModelPoint[]): [number, number | null][] {
  return toSeriesData(points, [0.75]); // 2 × 0.75 h = 90 min
}

export function unitLabel(unit: ModelsResponse["unit"]): string {
  return unit === "degF" ? "°F" : unit === "kt" ? "kt" : "%";
}

export function fmtValue(v: number | null, unit: ModelsResponse["unit"]): string {
  if (v === null) return "—";
  return unit === "degF" ? `${Math.round(v)}°F` : `${Math.round(v)} ${unit === "kt" ? "kt" : "%"}`;
}

export function fmtPointValue(p: ModelPoint, unit: ModelsResponse["unit"]): string {
  if (p.category) return `${p.category} (${CATEGORY_LABEL[p.category] ?? "category"})`;
  return fmtValue(p.value, unit) + (p.is_computed ? " (computed)" : "");
}

const NATIVE_LABEL: Record<string, string> = {
  degF: "°F", degC: "°C", K: "K", kt: "kt", mph: "mph", "m/s": "m/s", pct: "%",
  fraction: "fraction 0–1", category: "category", computed: "computed from T/Td",
}; // prettier-ignore

export function nativeUnitLabel(u: string | null): string {
  return u ? (NATIVE_LABEL[u] ?? u) : "—";
}

/** "06Z Nov 25" */
export function runLabel(iso: string): string {
  const d = new Date(iso);
  const mon = d.toLocaleString("en-US", { month: "short", timeZone: "UTC" });
  const hm =
    d.getUTCMinutes() === 0
      ? `${String(d.getUTCHours()).padStart(2, "0")}Z`
      : formatZulu(iso).replace(":", "");
  return `${hm} ${mon} ${d.getUTCDate()}`;
}

export function tooltipLines(
  m: ModelSeries,
  p: ModelPoint,
  unit: ModelsResponse["unit"],
  tz: string,
): string[] {
  const lines = [`${m.label} · ${m.producer}`];
  if (m.run) {
    lines.push(
      `Run ${runLabel(m.run.cycle_time)}${m.run.issuer ? ` (${m.run.issuer})` : ""} · received ${formatZulu(m.run.available_at)}`,
    );
  }
  lines.push(`Valid ${formatZulu(p.valid_time)} (${formatLocalTime(p.valid_time, tz)})`);
  lines.push(`Value ${fmtPointValue(p, unit)}`);
  lines.push(`Native unit ${nativeUnitLabel(m.native_unit)}`);
  if (m.grid?.distance_km !== null && m.grid?.distance_km !== undefined) {
    lines.push(
      `${m.grid.point_name ? "Point" : "Grid point"} ${m.grid.distance_km.toFixed(1)} km from the station`,
    );
  }
  return lines;
}

// ---------------------------------------------------------------- run lines + summary

export function runLine(m: ModelSeries, nowMs: number | null): string {
  if (!m.available || !m.run) return m.reason ?? "Not available";
  const r = m.run;
  const parts = [`run ${runLabel(r.cycle_time)}${r.issuer ? ` (${r.issuer})` : ""}`];
  parts.push(`received ${formatZulu(r.available_at)}`);
  if (r.status === "partial") {
    parts.push(`partial: ${r.steps_fetched} of ${r.steps_expected ?? "?"} steps so far`);
  }
  if (m.grid?.distance_km !== null && m.grid?.distance_km !== undefined) {
    parts.push(
      `${m.grid.point_name && m.group === "nws" ? "point" : "grid point"} ${m.grid.distance_km.toFixed(1)} km away` +
        (m.grid.height_m !== null && m.group !== "nws" ? `, model height ${Math.round(m.grid.height_m)} m` : ""),
    );
  }
  if (r.stale && nowMs !== null) {
    const h = Math.round((nowMs - Date.parse(r.available_at)) / 3600_000);
    parts.push(`stale: newest run received ${h} h ago`);
  }
  return parts.join(" · ");
}

function range(points: ModelPoint[], unit: ModelsResponse["unit"]): string | null {
  const v = points.map((p) => p.value).filter((x): x is number => x !== null);
  if (!v.length) return null;
  const lo = Math.min(...v);
  const hi = Math.max(...v);
  return lo === hi ? fmtValue(lo, unit) : `${fmtValue(lo, unit)}–${fmtValue(hi, unit)}`;
}

/** Text alternative for the chart (also shown under it). */
export function summarize(data: ModelsResponse, visible: Set<string>, tz: string): string {
  const v = VARIABLES.find((x) => x.key === data.variable)!;
  const w = data.window;
  const head =
    w.span === "today"
      ? `Model ${v.long} for the climate day ${w.climate_date} (${w.basis === "LST" ? "local standard time" : "local time"})`
      : `Model ${v.long} for 48 h from the start of the climate day ${w.climate_date}`;
  const parts: string[] = [];
  for (const m of data.models) {
    if (!visible.has(m.id) || !m.available) continue;
    if (m.kind === "categorical") {
      const cats = [...new Set(m.points.map((p) => p.category).filter(Boolean))];
      parts.push(`${m.label} ${m.run ? runLabel(m.run.cycle_time) : ""}: ${cats.join(", ") || "no values in this window"}`);
    } else {
      parts.push(`${m.label} ${m.run ? runLabel(m.run.cycle_time) : ""}: ${range(m.points, data.unit) ?? "no values in this window"}`);
    }
  }
  const obs = range(data.observed.points, data.unit);
  const obsText = obs
    ? `observed so far ${obs} (METAR, last ${formatZulu(data.observed.points.at(-1)!.valid_time)} / ${formatLocalTime(data.observed.points.at(-1)!.valid_time, tz)})`
    : "no observations in this window yet";
  const off = data.models.filter((m) => !m.available).map((m) => `${m.label} (${m.reason})`);
  return `${head}: ${parts.join("; ") || "no model shown"}; ${obsText}.${off.length ? ` Not shown: ${off.join("; ")}.` : ""}`;
}
