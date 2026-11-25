"use client";

import { usePolling } from "@/lib/hooks";
import { formatLocalTime, formatLocalWithZone, formatZulu, tzAbbrev } from "@/lib/time";
import type { CurrentResponse } from "@/lib/types";

import { RelativeAge } from "../RelativeAge";
import { FreshDot, StaleBadge } from "../states";

const card =
  "flex flex-col justify-between gap-3.5 rounded-[16px] border border-border bg-surface px-6 py-[22px]";
const big =
  "font-display text-[72px] leading-[0.9] font-semibold tracking-[-0.04em] sm:text-[96px]";

export function CurrentCards({ initial, tz }: { initial: CurrentResponse; tz: string }) {
  const { data, failed } = usePolling<CurrentResponse>(
    `/api/stations/${initial.station_id}/current`,
    initial,
  );
  const m = data.latest;
  const h = data.high_so_far;
  const stale = data.status !== "ok";
  const dayStart = formatLocalWithZone(data.climate_day.start, tz);

  return (
    <div className="grid flex-1 grid-cols-[repeat(auto-fit,minmax(240px,1fr))] gap-4">
      <section aria-labelledby="h-cur" className={card}>
        <h2 id="h-cur" className="text-sm font-semibold text-muted">
          Current temperature
        </h2>
        {m && m.temp_f !== null ? (
          <p className="flex items-start gap-1">
            <span className={big}>{m.temp_f}</span>
            <span className="pt-1.5 font-display text-[28px] font-medium text-muted">°F</span>
          </p>
        ) : (
          <p className="font-display text-[40px] font-semibold text-muted-2">—</p>
        )}
        <div className="flex flex-col gap-1.5 text-[13px] text-text-2">
          {m ? (
            <span className="flex items-center gap-2.5">
              <FreshDot stale={stale} />
              <span>
                Latest {m.report_type}{" "}
                <span className="font-mono">{formatZulu(m.observed_at)}</span> (
                {formatLocalWithZone(m.observed_at, tz)})
                <RelativeAge iso={m.observed_at} prefix=" · " />
              </span>
            </span>
          ) : (
            <span>No METAR received yet for this station.</span>
          )}
          {m && m.temp_f === null ? <span>The latest report has no temperature group.</span> : null}
          {stale && m ? <StaleBadge since={m.observed_at} /> : null}
          {failed ? (
            <span className="text-[#8A4100]">
              Couldn&apos;t refresh; showing the last data received.
            </span>
          ) : null}
        </div>
      </section>

      <section aria-labelledby="h-high" className={card}>
        <h2 id="h-high" className="text-sm font-semibold text-[#8A3A0E]">
          Today&apos;s high so far
        </h2>
        {h ? (
          <p className="flex items-start gap-1">
            <span className={`${big} text-temp`}>{h.value_f}</span>
            <span className="pt-1.5 font-display text-[28px] font-medium text-muted">°F</span>
          </p>
        ) : (
          <p className="font-display text-[40px] font-semibold text-muted-2">—</p>
        )}
        <p className="text-[13px] leading-normal text-text-2">
          {h ? (
            <>
              {h.kind === "max6h" ? "From the 6-hour maximum in the " : "From the "}
              <span className="font-mono">{formatZulu(h.observed_at)}</span> {h.report_type} (
              {formatLocalTime(h.observed_at, tz)} {tzAbbrev(h.observed_at, tz)}) · highest hourly
              METAR since local midnight. The daily summaries below include peaks between reports.
            </>
          ) : (
            <>
              No METAR with a temperature yet in today&apos;s climate day (it began at {dayStart},
              local standard time).
            </>
          )}
        </p>
      </section>
    </div>
  );
}
