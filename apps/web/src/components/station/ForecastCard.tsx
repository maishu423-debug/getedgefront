import { formatLocalTime, formatLocalWithZone } from "@/lib/time";
import type { ForecastResponse } from "@/lib/types";

import { RelativeAge } from "../RelativeAge";
import { NoData, StaleBadge, UpstreamDown } from "../states";

function hourLabel(iso: string, tz: string): string {
  // "7 AM" → "7a" style used by the design
  const t = formatLocalTime(iso, tz); // "7:00 AM"
  const m = /^(\d{1,2}):\d{2} ([AP])M$/.exec(t);
  return m ? `${m[1]}${m[2]!.toLowerCase()}` : t;
}

export function ForecastCard({
  fc,
  tz,
  failed,
}: {
  fc: ForecastResponse | null;
  tz: string;
  failed: boolean;
}) {
  return (
    <aside
      aria-labelledby="h-nws"
      className="min-w-0 flex-[1_1_340px] overflow-hidden rounded-[14px] border border-border bg-surface"
    >
      <div className="flex flex-col gap-1.5 border-b border-border px-[18px] py-4">
        <div className="flex items-center justify-between gap-2">
          <h2 id="h-nws" className="font-display text-base font-semibold">
            NWS forecast · Today
          </h2>
          <span className="rounded-full bg-badge-bg px-2 py-[3px] text-[10px] font-semibold tracking-[.06em] text-badge-text">
            FORECAST
          </span>
        </div>
        {fc && fc.status !== "no_data" ? (
          <span className="text-[12.5px] text-muted-2">
            National Weather Service{fc.office ? ` (${fc.office})` : ""} · updated{" "}
            {formatLocalWithZone(fc.update_time, tz)}
            {fc.status === "stale" ? (
              <>
                {" "}
                <StaleBadge since={fc.fetched_at} />
              </>
            ) : null}
          </span>
        ) : null}
      </div>
      <div className="flex flex-col gap-4 px-[18px] py-4">
        {failed || fc === null ? (
          <UpstreamDown what="The forecast" />
        ) : fc.status === "no_data" ? (
          <NoData what="NWS forecast" />
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-0.5 rounded-[10px] bg-[#FBF1EA] px-3.5 py-3">
                <span className="text-xs font-semibold text-[#8A3A0E]">Today · High</span>
                <span className="font-display text-[30px] font-semibold">
                  {fc.today_high_f !== null ? `${fc.today_high_f}°F` : "—"}
                </span>
              </div>
              <div className="flex flex-col gap-0.5 rounded-[10px] bg-[#EAF0F7] px-3.5 py-3">
                <span className="text-xs font-semibold text-[#1D4F8A]">
                  {fc.tonight?.name ?? "Tonight"} · Low
                </span>
                <span className="font-display text-[30px] font-semibold">
                  {fc.tonight_low_f !== null ? `${fc.tonight_low_f}°F` : "—"}
                </span>
              </div>
            </div>
            {fc.today_note ? <p className="text-[12.5px] text-muted-2">{fc.today_note}</p> : null}
            <div className="flex flex-col gap-2.5 text-[13.5px] leading-normal">
              {fc.today ? (
                <p>
                  <strong>{fc.today.name}:</strong> {fc.today.detailed ?? fc.today.short}
                </p>
              ) : null}
              {fc.tonight ? (
                <p>
                  <strong>{fc.tonight.name}:</strong> {fc.tonight.detailed ?? fc.tonight.short}
                </p>
              ) : null}
            </div>
            {fc.hourly.length ? (
              <div className="flex flex-col gap-2">
                <span className="text-xs font-semibold text-muted">Hourly (local time)</span>
                <ol
                  className="grid grid-cols-7 gap-1"
                  aria-label="Hourly forecast, temperature and chance of precipitation"
                >
                  {fc.hourly.map((h) => (
                    <li
                      key={h.start}
                      className="flex flex-col items-center gap-1 rounded-[8px] bg-page px-0.5 py-2"
                      aria-label={`${formatLocalTime(h.start, tz)}: ${h.temperature_f ?? "no"} degrees, ${h.pop_percent ?? "unknown"} percent chance of precipitation`}
                    >
                      <span className="text-[11px] text-muted-2">{hourLabel(h.start, tz)}</span>
                      <span className="font-mono text-sm font-semibold">
                        {h.temperature_f !== null ? `${h.temperature_f}°` : "—"}
                      </span>
                      <span className="font-mono text-[10.5px] text-muted-2">
                        {h.pop_percent !== null ? `${h.pop_percent}%` : "—"}
                      </span>
                    </li>
                  ))}
                </ol>
                <span className="text-[11.5px] text-muted-2">
                  Bottom row: chance of precipitation
                </span>
              </div>
            ) : null}
          </>
        )}
        <div className="border-t border-hairline pt-3 text-xs text-muted-2">
          Shown as published by the NWS
          {fc?.fetched_at ? <RelativeAge iso={fc.fetched_at} prefix=" · received " /> : null}.
          EdgeFront does not make forecasts.{" "}
          {fc?.weather_gov_url ? (
            <a href={fc.weather_gov_url}>Full forecast on weather.gov</a>
          ) : null}
        </div>
      </div>
    </aside>
  );
}
