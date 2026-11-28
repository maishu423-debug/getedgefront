/**
 * Which stations have 5-minute data (v2 Phase 10 fixes, owner: "coverage honesty"). Counted from
 * the station registry (data/stations.yaml `five_minute_feed`, copied at build time into
 * src/generated/stations.json), never hard-coded, so every "26 of 28" on the site stays true.
 */
import registry from "@/generated/stations.json";

type Entry = { id: string; name: string; fiveMinute?: boolean };

const ALL: Entry[] = registry.stations;

/** "Central Park" from "New York · Central Park"; the full name when there is no "·". */
export function shortName(name: string): string {
  const parts = name.split(" · ");
  return parts.length > 1 ? parts.slice(1).join(" · ") : name;
}

export function coverage(stations: Entry[] = ALL) {
  const outside = stations.filter((s) => s.fiveMinute === false);
  const total = stations.length;
  const inFeed = total - outside.length;
  const names = outside.map((s) => `${s.id} ${shortName(s.name)}`);
  const not = names.length ? ` (not ${names.join(names.length === 2 ? " or " : ", ")})` : "";
  return {
    total,
    inFeed,
    outside: outside.map((s) => s.id),
    /** "26 of 28 stations" or "all 28 stations" */
    count: inFeed === total ? `all ${total} stations` : `${inFeed} of ${total} stations`,
    /** "5-minute data for 26 of 28 stations (not KNYC Central Park or KBKF Buckley)" */
    sentence: `5-minute data for ${inFeed === total ? `all ${total}` : `${inFeed} of ${total}`} stations${not}`,
    /** "(not KNYC Central Park or KBKF Buckley)" or "" */
    exceptions: not.trim(),
  };
}

export const COVERAGE = coverage();

export function inFiveMinuteFeed(stationId: string): boolean {
  return ALL.find((s) => s.id === stationId)?.fiveMinute !== false;
}

/** The note on a station outside the feed, for every viewer (free and Premium alike). */
export const NOT_IN_FEED_NOTE =
  "This station isn't in the 5-minute feed. Values are from the hourly METAR.";
