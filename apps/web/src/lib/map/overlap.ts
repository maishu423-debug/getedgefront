/**
 * Keeps every station reachable on the map (v2 Phase 10 B5). Markers whose boxes (real on-screen
 * width, 26 px tall, plus a small margin) would overlap are grouped:
 * - small groups (up to MAX_SPREAD) are spread on a circle around their centre, wide enough that
 *   neighbours never touch, whatever their direction;
 * - bigger groups (zoomed far out, e.g. a phone showing the whole country) become one cluster
 *   button with the count; selecting it zooms in on its stations.
 * The list next to the map always has every station. Pure: input is each marker's projected
 * pixel position and width; recomputed after every zoom, so groups merge and split.
 */
export interface Px {
  id: string;
  x: number;
  y: number;
  /** on-screen width of the marker (px); default 34 */
  w?: number;
}

export interface Cluster {
  ids: string[];
  x: number;
  y: number;
}

export interface Layout {
  offsets: Map<string, [number, number]>;
  clusters: Cluster[];
}

export const MARKER_H = 26;
export const MAX_SPREAD = 4;
const GAP = 6;

function overlaps(a: Px, b: Px): boolean {
  const wa = a.w ?? 34;
  const wb = b.w ?? 34;
  return Math.abs(a.x - b.x) < (wa + wb) / 2 + GAP && Math.abs(a.y - b.y) < MARKER_H + GAP;
}

export function layout(points: Px[], maxSpread = MAX_SPREAD): Layout {
  const offsets = new Map<string, [number, number]>();
  const clusters: Cluster[] = [];
  const groups: Px[][] = [];
  // single-link grouping: a marker joins every group it overlaps (groups merge)
  for (const p of points) {
    const near = groups.filter((g) => g.some((q) => overlaps(p, q)));
    const merged = [p, ...near.flat()];
    for (const g of near) groups.splice(groups.indexOf(g), 1);
    groups.push(merged);
  }
  for (const g of groups) {
    if (g.length === 1) {
      offsets.set(g[0]!.id, [0, 0]);
      continue;
    }
    const cx = g.reduce((s, p) => s + p.x, 0) / g.length;
    const cy = g.reduce((s, p) => s + p.y, 0) / g.length;
    if (g.length > maxSpread) {
      clusters.push({ ids: g.map((p) => p.id).sort(), x: cx, y: cy });
      continue;
    }
    // neighbours on the circle are `need` apart (chord = 2r·sin(π/n)); `need` covers the widest
    // marker, so two markers never touch even when they end up side by side
    const need = Math.max(...g.map((p) => p.w ?? 34)) + GAP;
    const r = need / (2 * Math.sin(Math.PI / g.length));
    // stable order around the circle: by angle from the centre (west → east for a pair)
    const sorted = g
      .slice()
      .sort((a, b) => Math.atan2(a.y - cy, a.x - cx) - Math.atan2(b.y - cy, b.x - cx));
    const start = Math.atan2(sorted[0]!.y - cy, sorted[0]!.x - cx);
    sorted.forEach((p, i) => {
      const a = start + (2 * Math.PI * i) / g.length;
      offsets.set(p.id, [
        Math.round(cx + r * Math.cos(a) - p.x),
        Math.round(cy + r * Math.sin(a) - p.y),
      ]);
    });
  }
  return { offsets, clusters };
}

/** Offsets only (every group spread): kept for callers that never cluster. */
export function spread(points: Px[]): Map<string, [number, number]> {
  return layout(points, Infinity).offsets;
}
