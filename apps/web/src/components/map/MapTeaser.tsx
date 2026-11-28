/* eslint-disable @next/next/no-img-element -- a static SVG from public/, no optimisation needed */
import { TrialButton } from "../billing/TrialButton";
import { LockIcon } from "../LockIcon";

/**
 * The map for free and signed-out visitors (v2 Phase 10 B5): a static picture of the outline
 * with no data values, three benefits and the trial button. No map library, no tiles, no data.
 */
export const MAP_BENEFITS = [
  "Every settlement station on one map, coloured by the current temperature or today's high or low so far.",
  "5-minute ASOS readings, refreshed every minute, with the hourly METAR shown for comparison.",
  "Filter by Kalshi, Polymarket or Robinhood, and open any station's full page from the map.",
];

export function MapTeaser() {
  return (
    <div className="flex flex-col gap-4" data-testid="map-teaser">
      <div className="flex flex-col gap-1">
        <h1 className="font-display text-[32px] font-bold tracking-[-0.02em]">Live station map</h1>
        <p className="text-sm text-muted">
          5-minute ASOS data for every settlement station · Premium
        </p>
      </div>
      <div className="flex flex-wrap items-start gap-4">
        <div className="relative min-w-0 flex-[999_1_620px] overflow-hidden rounded-[16px] border border-border bg-[#EAF1F4] p-3">
          <img
            src="/map/us-outline.svg"
            alt="Outline of the contiguous United States (illustration, no data)"
            width={1000}
            height={560}
            className="block h-auto w-full opacity-80"
          />
          <span className="absolute top-4 left-4 inline-flex items-center gap-1.5 rounded-full bg-premium-bg px-3 py-1.5 text-[12px] font-semibold tracking-[.04em] text-premium-text">
            <LockIcon />
            PREMIUM
          </span>
        </div>
        <section
          aria-labelledby="h-teaser"
          className="flex min-w-0 flex-[1_1_300px] flex-col gap-3.5 rounded-[16px] border border-border bg-surface p-5"
        >
          <h2 id="h-teaser" className="font-display text-xl font-semibold">
            See every station at once
          </h2>
          <ul className="flex flex-col gap-2.5 text-[14px] leading-normal text-text-2">
            {MAP_BENEFITS.map((b) => (
              <li key={b} className="flex gap-2.5">
                <span aria-hidden className="mt-[7px] size-1.5 flex-none rounded-full bg-brand" />
                {b}
              </li>
            ))}
          </ul>
          <TrialButton />
        </section>
      </div>
    </div>
  );
}
