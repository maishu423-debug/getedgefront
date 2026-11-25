/** Gaps between consecutive reports (and the window edges) longer than `gapMinutes`.
 * Mirrors the API rule: no line is ever drawn across such a gap. */
export interface GapMs {
  startMs: number;
  endMs: number;
  minutes: number;
}

export function findGaps(
  timesMs: number[],
  windowStartMs: number,
  windowEndMs: number,
  gapMinutes = 90,
): GapMs[] {
  const edges = [
    windowStartMs,
    ...timesMs.filter((t) => t >= windowStartMs && t <= windowEndMs),
    windowEndMs,
  ];
  const out: GapMs[] = [];
  for (let i = 1; i < edges.length; i++) {
    const a = edges[i - 1]!;
    const b = edges[i]!;
    const minutes = Math.floor((b - a) / 60000);
    if (minutes > gapMinutes) out.push({ startMs: a, endMs: b, minutes });
  }
  return out;
}

/** Series values with `null` inserted inside gaps so chart lines break there. */
export function breakAtGaps<T>(
  points: { t: number; v: T | null }[],
  gapMinutes = 90,
): [number, T | null][] {
  const out: [number, T | null][] = [];
  for (let i = 0; i < points.length; i++) {
    const p = points[i]!;
    if (i > 0 && p.t - points[i - 1]!.t > gapMinutes * 60000) {
      out.push([points[i - 1]!.t + 60000, null]);
    }
    out.push([p.t, p.v]);
  }
  return out;
}
