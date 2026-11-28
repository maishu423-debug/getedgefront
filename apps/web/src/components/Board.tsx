"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { climateDayBounds, elapsedFraction, formatCountdown } from "@/lib/climate";
import { useNow, usePolling } from "@/lib/hooks";
import { usePremiumData, usePremiumTier } from "@/lib/premium/client";
import type { MapResponse, MapStation } from "@/lib/premium/types";
import { fmtFExact, spokenTemp, type TempValue } from "@/lib/temp";
import { formatLocalTime, formatLocalWithZone, formatZulu } from "@/lib/time";
import type { BoardRow, StationsResponse, Venue } from "@/lib/types";

import { RelativeAge } from "./RelativeAge";

export const VENUE_LABEL: Record<Venue, string> = {
  kalshi: "Kalshi",
  polymarket: "Polymarket",
  robinhood: "Robinhood",
};
const VENUES: (Venue | "all")[] = ["all", "kalshi", "polymarket", "robinhood"];

export function VenueTags({ venues }: { venues: BoardRow["venues"] }) {
  const names = [...new Set(venues.map((v) => v.venue))];
  return (
    <span className="flex flex-wrap gap-1">
      {names.map((v) => (
        <span
          key={v}
          className="inline-block rounded-[5px] border border-border bg-[#EEF1EE] px-[7px] py-[2px] text-[11px] font-medium text-[#3A4644]"
        >
          {VENUE_LABEL[v]}
        </span>
      ))}
    </span>
  );
}

function Tabs<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: [T, string][];
  onChange: (v: T) => void;
}) {
  return (
    <div role="group" aria-label={label} className="flex rounded-[9px] bg-[#E7EAE6] p-[3px]">
      {options.map(([v, text]) => (
        <button
          key={v}
          type="button"
          aria-pressed={value === v}
          onClick={() => onChange(v)}
          className={`min-h-10 cursor-pointer rounded-[7px] px-3 text-[13px] font-medium whitespace-nowrap focus-visible:ring-2 focus-visible:ring-brand/50 focus-visible:outline-none ${
            value === v
              ? "bg-surface text-ink shadow-[0_1px_2px_rgba(16,26,28,.14)]"
              : "text-muted hover:text-ink"
          }`}
        >
          {text}
        </button>
      ))}
    </div>
  );
}

function GroupHeader({ rows, now }: { rows: BoardRow[]; now: number | null }) {
  const first = rows[0]!;
  // Before mount: server-provided values; after mount: live, from the station tz (never the browser's).
  const bounds = now !== null ? climateDayBounds(now, first.tz) : null;
  const left =
    bounds && now !== null
      ? formatCountdown(bounds.endMs, now)
      : formatCountdown(first.climate_day.ends_in_minutes * 60000, 0);
  const pct =
    bounds && now !== null ? elapsedFraction(bounds, now) : first.climate_day.elapsed_fraction;
  const local = formatLocalWithZone(
    now !== null ? new Date(now).toISOString() : first.local_time,
    first.tz,
  );
  return (
    <tr>
      <td colSpan={8} className="border-b border-border bg-[#F1F4F1] px-3.5 py-[9px]">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-[13px] font-semibold">
            {first.zone_group} <span className="font-normal text-muted">· local time {local}</span>
          </span>
          <span className="flex items-center gap-2 text-xs text-text-2">
            Local day ends in <span className="font-mono font-semibold">{left}</span>
            <span
              role="progressbar"
              aria-label={`${first.zone_group} climate day elapsed`}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(pct * 100)}
              className="inline-block h-1.5 w-[90px] overflow-hidden rounded-[3px] bg-border"
            >
              <span
                className="block h-1.5 bg-brand"
                style={{ width: `${(pct * 100).toFixed(1)}%` }}
              />
            </span>
          </span>
        </div>
      </td>
    </tr>
  );
}

/** The small marker on Premium 5-minute values (B6). */
function FiveMin() {
  return (
    <span className="ml-1 rounded-[4px] bg-[#E6F2F1] px-1 py-px align-[2px] font-sans text-[9.5px] font-semibold tracking-[.04em] text-[#064F4B]">
      5-MIN
    </span>
  );
}

/** Fresh 5-minute values for a row, else null (no data, delayed: the row keeps METAR). */
function fiveMinFor(hf: MapStation | undefined): MapStation | null {
  return hf && hf.in_feed && hf.status === "ok" && hf.hf_latest?.temp ? hf : null;
}

function Row({ r, hf }: { r: BoardRow; hf?: MapStation }) {
  const href = `/station/${r.id}`;
  const five = fiveMinFor(hf);
  const metarNow = r.latest?.temp
    ? `Hourly METAR ${formatZulu(r.latest.observed_at)}: ${r.latest.temp.f_rounded}° (${fmtFExact(r.latest.temp)} °F)`
    : "No hourly METAR";
  return (
    <tr className="hover:bg-[#F7FAF9]">
      <td className="px-2.5 py-2.5">
        <Link href={href} className="flex flex-col gap-px text-ink no-underline">
          <span className="font-mono text-sm font-semibold text-brand">{r.id}</span>
          <span className="block max-w-[172px] text-[12.5px] whitespace-normal text-[#3A4644]">
            {r.name}
          </span>
        </Link>
      </td>
      <td className="px-2.5 py-2.5">
        <VenueTags venues={r.venues} />
      </td>
      <td className="px-2.5 py-2.5 text-right font-mono text-[15px]">
        {five ? (
          <span
            title={`${spokenTemp("Now, 5-minute", five.hf_latest!.temp!, formatLocalTime(five.hf_latest!.observed_at, r.tz))}. ${metarNow}`}
            data-testid="board-5min"
          >
            {five.hf_latest!.temp!.f_rounded}°
            <FiveMin />
          </span>
        ) : (
          <>
            {r.latest?.temp_f ?? "—"}
            {r.latest?.temp_f != null ? "°" : ""}
          </>
        )}
      </td>
      <td className="px-2.5 py-2.5 text-right">
        {five?.hf_so_far.high ? (
          <SoFar
            label="High so far, 5-minute"
            value={five.hf_so_far.high.temp.f_rounded}
            temp={five.hf_so_far.high.temp}
            at={formatLocalTime(five.hf_so_far.high.observed_at, r.tz)}
            className="text-high"
            badge={<FiveMin />}
            note={
              r.high_so_far?.temp
                ? `Highest hourly METAR: ${r.high_so_far.temp.f_rounded}° (${fmtFExact(r.high_so_far.temp)} °F)`
                : "No hourly METAR high yet"
            }
          />
        ) : r.high_so_far ? (
          <SoFar
            label="High so far"
            value={r.high_so_far.value_f}
            temp={r.high_so_far.temp}
            at={formatLocalTime(r.high_so_far.observed_at, r.tz)}
            className="text-high"
            badge={
              r.fresh_high ? (
                <span className="ml-1.5 rounded-[4px] bg-[#FBE9DD] px-[5px] py-px align-[2px] font-sans text-[10px] font-semibold text-[#8A3A0E]">
                  NEW
                </span>
              ) : null
            }
          />
        ) : (
          <span className="text-muted-2">—</span>
        )}
      </td>
      <td className="px-2.5 py-2.5 text-right">
        {five?.hf_so_far.low ? (
          <SoFar
            label="Low so far, 5-minute"
            value={five.hf_so_far.low.temp.f_rounded}
            temp={five.hf_so_far.low.temp}
            at={formatLocalTime(five.hf_so_far.low.observed_at, r.tz)}
            className="text-[#1F5E8C]"
            badge={<FiveMin />}
            note={
              r.low_so_far?.temp
                ? `Lowest hourly METAR: ${r.low_so_far.temp.f_rounded}° (${fmtFExact(r.low_so_far.temp)} °F)`
                : "No hourly METAR low yet"
            }
          />
        ) : r.low_so_far ? (
          <SoFar
            label="Low so far"
            value={r.low_so_far.value_f}
            temp={r.low_so_far.temp}
            at={formatLocalTime(r.low_so_far.observed_at, r.tz)}
            className="text-[#1F5E8C]"
          />
        ) : (
          <span className="text-muted-2">—</span>
        )}
      </td>
      <td className="px-2.5 py-2.5 text-right font-mono text-sm text-[#3A4644]">
        {r.nws_today_high_f != null ? `${r.nws_today_high_f}°` : "—"}
      </td>
      <td className="px-2.5 py-2.5">
        {r.latest ? (
          <div className="flex flex-col gap-px">
            <span
              className={`font-mono text-[13px] ${r.is_stale ? "font-semibold text-[#8A4100]" : ""}`}
            >
              {formatZulu(r.latest.observed_at)}
              {r.latest.report_type === "SPECI" ? (
                <span className="ml-1 text-[10.5px] text-premium-text">SPECI</span>
              ) : null}
            </span>
            <span
              className={`text-[11.5px] ${r.is_stale ? "font-semibold text-[#8A4100]" : "text-muted-2"}`}
            >
              {r.is_stale ? "Stale · " : ""}
              <RelativeAge iso={r.latest.observed_at} />
            </span>
          </div>
        ) : (
          <span className="text-[12px] text-muted-2">No report yet</span>
        )}
      </td>
      <td className="px-2 py-2.5 text-right">
        <Link
          href={href}
          aria-label={`Open ${r.id}`}
          className="inline-flex size-10 items-center justify-center rounded-[8px] text-muted hover:bg-[#EEF1EE]"
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            aria-hidden
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <path d="M9 6l6 6-6 6" />
          </svg>
        </Link>
      </td>
    </tr>
  );
}

export function Board({ initial }: { initial: StationsResponse }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const now = useNow(30_000);
  const { data, failed } = usePolling<StationsResponse>("/api/stations", initial);
  const { premium } = usePremiumTier();
  const pm = usePremiumData<MapResponse>("/api/premium/map", premium);
  const hfBy = new Map((pm.data?.stations ?? []).map((x) => [x.station_id, x]));
  const anyFive = premium && [...hfBy.values()].some((x) => fiveMinFor(x));

  const venueParam = params.get("venue");
  const venue: Venue | "all" = (VENUES as string[]).includes(venueParam ?? "")
    ? (venueParam as Venue)
    : "all";
  const sort: "tz" | "az" = params.get("sort") === "az" ? "az" : "tz";

  const setParam = (k: "venue" | "sort", v: string, dflt: string) => {
    const next = new URLSearchParams(params.toString());
    if (v === dflt) next.delete(k);
    else next.set(k, v);
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };

  const rows = data.stations.filter(
    (r) => venue === "all" || r.venues.some((v) => v.venue === venue),
  );
  const groups: BoardRow[][] =
    sort === "az"
      ? [rows.slice().sort((a, b) => a.name.localeCompare(b.name))]
      : [...new Set(rows.map((r) => r.std_utc_offset_minutes))]
          .sort((a, b) => b - a) // east → west
          .map((off) => rows.filter((r) => r.std_utc_offset_minutes === off));

  return (
    <section aria-labelledby="h-board" className="flex min-w-0 flex-[999_1_760px] flex-col gap-3.5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-col gap-0.5">
          <h2 id="h-board" className="font-display text-[22px] font-semibold">
            Settlement stations
          </h2>
          <span className="text-[13px] text-muted-2">
            {rows.length} stations ·{" "}
            {anyFive
              ? "5-minute ASOS values (5-MIN) where available, else the latest hourly METAR"
              : "current values from the latest hourly METAR"}
            {premium && pm.failed ? " · 5-minute data: connection lost, retrying" : ""}
          </span>
        </div>
        <div className="flex flex-wrap gap-2.5">
          <Tabs
            label="Venue"
            value={venue}
            options={[
              ["all", "All"],
              ["kalshi", "Kalshi"],
              ["polymarket", "Polymarket"],
              ["robinhood", "Robinhood"],
            ]}
            onChange={(v) => setParam("venue", v, "all")}
          />
          <Tabs
            label="Sort"
            value={sort}
            options={[
              ["tz", "By time zone"],
              ["az", "A–Z"],
            ]}
            onChange={(v) => setParam("sort", v, "tz")}
          />
        </div>
      </div>
      {failed ? (
        <p
          role="status"
          className="rounded-[8px] bg-warn-halo px-3 py-2 text-[13px] text-[#6B4600]"
        >
          Couldn&apos;t refresh the board. Showing the data from {formatZulu(data.generated_at)}.
        </p>
      ) : null}
      {data.status === "no_data" ? (
        <p
          role="status"
          className="rounded-[10px] border border-border bg-[#FAFBF9] px-4 py-3 text-sm"
        >
          No METARs received yet. The board fills in after the first fetch.
        </p>
      ) : null}
      <div className="overflow-hidden rounded-[14px] border border-border bg-surface">
        <div
          className="relative overflow-x-auto focus-visible:ring-2 focus-visible:ring-brand/50 focus-visible:outline-none"
          tabIndex={0}
          role="region"
          aria-label="Settlement stations table"
        >
          <table className="w-full border-collapse text-[13.5px] [&_td]:border-b [&_td]:border-hairline [&_td]:whitespace-nowrap">
            <caption className="sr-only">
              Settlement stations with current temperature, high and low so far (rounded and
              unrounded °F), NWS forecast high and last METAR
            </caption>
            <thead>
              <tr className="[&_th]:border-b [&_th]:border-border [&_th]:bg-[#FAFBF9] [&_th]:px-2.5 [&_th]:py-2.5 [&_th]:text-[11px] [&_th]:font-semibold [&_th]:tracking-[.04em] [&_th]:whitespace-nowrap [&_th]:text-muted-2 [&_th]:uppercase">
                <th scope="col" className="text-left">
                  Station
                </th>
                <th scope="col" className="text-left">
                  Venues
                </th>
                <th scope="col" className="text-right">
                  Now
                </th>
                <th scope="col" className="text-right">
                  High so far
                </th>
                <th scope="col" className="text-right">
                  Low so far
                </th>
                <th scope="col" className="text-right !whitespace-normal">
                  NWS fcst high
                </th>
                <th scope="col" className="text-left">
                  Last METAR
                </th>
                <th scope="col">
                  <span className="sr-only">Open</span>
                </th>
              </tr>
            </thead>
            {groups.map((g) =>
              g.length ? (
                <tbody key={sort === "az" ? "az" : g[0]!.std_utc_offset_minutes}>
                  {sort === "tz" ? <GroupHeader rows={g} now={now} /> : null}
                  {g.map((r) => (
                    <Row key={r.id} r={r} hf={hfBy.get(r.id)} />
                  ))}
                </tbody>
              ) : null,
            )}
          </table>
        </div>
      </div>
      <p className="text-xs text-muted-2">
        High / low so far = highest / lowest hourly METAR since local midnight (local standard time)
        {anyFive ? ", or of the 5-minute readings where marked 5-MIN" : ""}; the small number is the
        unrounded °F. It is not a settlement value: markets settle on each venue&apos;s named source
        (an NWS climate report or another provider), which can differ. Read the market&apos;s rules.
      </p>
    </section>
  );
}

/** A high/low-so-far cell: whole °F, then "at 2:53 PM · 62.96°" (unrounded) on the second line. */
function SoFar({
  label,
  value,
  temp,
  at,
  className,
  badge = null,
  note = "",
}: {
  label: string;
  value: number;
  temp?: TempValue;
  at: string;
  className: string;
  badge?: ReactNode;
  /** extra tooltip text, e.g. the METAR value next to a 5-minute one */
  note?: string;
}) {
  const spoken = temp ? spokenTemp(label, temp, at) : `${label} ${value} °F, at ${at}`;
  return (
    <div className="flex flex-col items-end gap-px" title={note ? `${spoken}. ${note}` : spoken}>
      <span className={`font-mono text-[15px] font-semibold ${className}`}>
        {value}°{badge}
      </span>
      <span className="text-[11.5px] text-muted-2">
        at {at}
        {temp ? <span className="font-mono"> · {fmtFExact(temp)}°</span> : null}
      </span>
    </div>
  );
}
