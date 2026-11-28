import { describe, expect, it } from "vitest";

import type { HfReading } from "@/lib/premium/types";

import { tableItems } from "./hfTable";

const r = (iso: string) => ({ observed_at: iso }) as HfReading;

describe("5-minute table rows", () => {
  it("newest first, a divider per UTC hour, one muted row per gap", () => {
    const times = [
      "2026-11-28T20:50:00Z", "2026-11-28T20:55:00Z", "2026-11-28T21:00:00Z",
      // 21:05–21:25 missing
      "2026-11-28T21:30:00Z", "2026-11-28T21:35:00Z",
      // 21:40 missing
      "2026-11-28T21:45:00Z",
    ]; // prettier-ignore
    const items = tableItems(times.map(r), 2, "America/Chicago");
    expect(items.map((i) => (i.kind === "row" ? i.r.observed_at.slice(11, 16) : i.kind === "gap" ? i.label : `[${i.label}]`))).toEqual([
      "[21Z · 3 PM]", "21:45", "No reading at 21:40Z", "21:35", "21:30", "No readings 21:05Z–21:25Z", "21:00",
      "[20Z · 2 PM]", "20:55", "20:50",
    ]); // prettier-ignore
  });
  it("keeps only the chosen window, counted back from the newest reading", () => {
    const times = Array.from({ length: 48 }, (_, i) => new Date(Date.parse("2026-11-28T18:00:00Z") + i * 300_000).toISOString()); // prettier-ignore
    const rows = (h: number) => tableItems(times.map(r), h, "UTC").filter((i) => i.kind === "row");
    expect(rows(2)).toHaveLength(24);
    expect(rows(6)).toHaveLength(48);
    expect(tableItems([], 2, "UTC")).toEqual([]);
  });
});
