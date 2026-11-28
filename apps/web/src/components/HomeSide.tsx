import { COVERAGE } from "@/lib/coverage";
import Link from "next/link";

import { formatZulu } from "@/lib/time";
import type { FeedResponse } from "@/lib/types";

import { LockIcon } from "./Chrome";
import { NoData, UpstreamDown } from "./states";

export function NewHighsFeed({ feed }: { feed: FeedResponse | null }) {
  return (
    <section
      aria-labelledby="h-new"
      className="overflow-hidden rounded-[14px] border border-border bg-surface"
    >
      <div className="flex flex-col gap-0.5 border-b border-border px-[18px] py-4">
        <h2 id="h-new" className="font-display text-[17px] font-semibold">
          Recent new highs
        </h2>
        <span className="text-[12.5px] text-muted-2">
          A station&apos;s METAR beat its earlier high for the local day
        </span>
      </div>
      {feed === null ? (
        <div className="p-4">
          <UpstreamDown what="The EdgeFront API" />
        </div>
      ) : feed.events.length === 0 ? (
        <div className="p-4">
          <NoData what="new highs">No station has raised its high yet today.</NoData>
        </div>
      ) : (
        <ol className="m-0 list-none p-0">
          {feed.events.map((e) => (
            <li
              key={`${e.station_id}-${e.report_id}`}
              className="border-b border-hairline last:border-b-0"
            >
              <Link
                href={`/station/${e.station_id}`}
                className="grid min-h-11 grid-cols-[64px_minmax(0,1fr)_auto] items-center gap-2.5 px-[18px] py-2.5 text-ink no-underline hover:bg-[#F7FAF9]"
              >
                <span className="font-mono text-xs text-muted-2">{formatZulu(e.observed_at)}</span>
                <span className="flex min-w-0 flex-col gap-px">
                  <span className="font-mono text-[13px] font-semibold">{e.station_id}</span>
                  <span className="truncate text-xs text-muted">{e.station_name}</span>
                </span>
                <span className="font-mono text-[13px] whitespace-nowrap">
                  <span className="text-muted-2">{e.from_f}°</span> →{" "}
                  <span className="font-semibold text-high">{e.to_f}°F</span>
                </span>
              </Link>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

/** Locked Premium teaser. A static, blurred illustration — deliberately not a working map. */
export function MapTeaser() {
  return (
    <section
      aria-labelledby="h-map"
      className="relative min-h-[280px] overflow-hidden rounded-[14px] border border-border bg-[#E9EEEC]"
    >
      <svg viewBox="0 0 360 280" width="100%" height="280" aria-hidden className="block blur-[3px]">
        <rect width="360" height="280" fill="#E3EAE7" />
        <path
          d="M30 90 C70 60 140 55 200 62 S300 70 330 100 S320 190 280 215 S170 235 120 220 S40 175 30 90 Z"
          fill="#D2DCD8"
        />
        <g fill="#9DB3AE">
          {[
            [300, 105],
            [276, 140],
            [262, 188],
            [230, 112],
            [200, 170],
            [150, 130],
            [120, 185],
            [62, 168],
            [70, 92],
            [232, 78],
          ].map(([x, y]) => (
            <circle key={`${x}-${y}`} cx={x} cy={y} r="5" />
          ))}
        </g>
      </svg>
      <div className="absolute inset-0 flex flex-col justify-end gap-2.5 bg-[linear-gradient(180deg,rgba(244,245,242,0)_25%,rgba(244,245,242,.97)_70%)] p-[18px]">
        <span className="inline-flex items-center gap-1.5 self-start rounded-full bg-premium-bg px-[9px] py-1 text-[10.5px] font-semibold tracking-[.06em] text-premium-text">
          <LockIcon size={11} />
          PREMIUM
        </span>
        <h2 id="h-map" className="font-display text-[19px] font-semibold">
          Live station map
        </h2>
        <p className="text-[13px] leading-normal text-text-2">
          Every settlement station on one map, with {COVERAGE.sentence}. Part of Premium.
        </p>
        <Link
          href="/map"
          className="inline-flex min-h-10 items-center self-start rounded-[9px] bg-ink px-4 text-sm font-semibold text-white no-underline hover:bg-[#25302F] hover:text-white"
        >
          Open the map
        </Link>
      </div>
    </section>
  );
}
