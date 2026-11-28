/**
 * Live map settings (v2 Phase 10 B5, Q32: OpenFreeMap + a bundled outline as backup).
 * NEXT_PUBLIC_MAP_STYLE_URL is built into the browser bundle (not a secret).
 */
import pkg from "maplibre-gl/package.json";

export const DEFAULT_STYLE_URL = "https://tiles.openfreemap.org/styles/positron";

export function styleUrl(): string {
  return process.env.NEXT_PUBLIC_MAP_STYLE_URL || DEFAULT_STYLE_URL;
}

/** MapLibre's worker, copied to public/vendor at build time (scripts/copy-maplibre-worker.mjs). */
export const WORKER_URL = `/vendor/maplibre-gl-worker-${pkg.version}.mjs`;

/** The street map must be up within this long, else the outline is shown. */
export const STYLE_TIMEOUT_MS = 8_000;

/** Contiguous U.S. with some room; panning and zooming stay around it. */
export const MAX_BOUNDS: [[number, number], [number, number]] = [
  [-150, 8],
  [-45, 62],
];

export const OUTLINE_ATTRIBUTION =
  "Outline: U.S. Census Bureau cartographic boundaries (public domain)";

/** The backup basemap: our own file only, no glyphs, sprites or tiles from anywhere else. */
export const OUTLINE_STYLE = {
  version: 8 as const,
  sources: {
    outline: {
      type: "geojson" as const,
      data: "/map/us-outline.json",
      attribution: OUTLINE_ATTRIBUTION,
    },
  },
  layers: [
    { id: "bg", type: "background" as const, paint: { "background-color": "#EAF1F4" } },
    {
      id: "land",
      type: "fill" as const,
      source: "outline",
      filter: ["==", ["get", "kind"], "land"],
      paint: { "fill-color": "#F7F8F4" },
    },
    {
      id: "borders",
      type: "line" as const,
      source: "outline",
      filter: ["==", ["get", "kind"], "borders"],
      paint: { "line-color": "#D2D9D5", "line-width": 0.8 },
    },
    {
      id: "edge",
      type: "line" as const,
      source: "outline",
      filter: ["==", ["get", "kind"], "edge"],
      paint: { "line-color": "#A9B7B1", "line-width": 1.3 },
    },
  ],
};
