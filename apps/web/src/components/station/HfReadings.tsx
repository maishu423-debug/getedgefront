"use client";

import { memo, useEffect, useMemo, useRef, useState } from "react";

import { inFiveMinuteFeed } from "@/lib/coverage";
import { useNow } from "@/lib/hooks";
import { usePremiumData, usePremiumTier } from "@/lib/premium/client";
import type { HfReading, HfSeriesResponse } from "@/lib/premium/types";
import { conversionTooltip, fmtC, fmtFExact, tempFromC } from "@/lib/temp";
import { formatLocalTime, formatZulu, minutesSince } from "@/lib/time";
import { skyText } from "@/lib/units";

import { TrialButton } from "../billing/TrialButton";
import { LockIcon } from "../LockIcon";
import { NoData, Skeleton, UpstreamDown } from "../states";
import { QC_FLAGGED, QC_MEANING, tableItems } from "./hfTable";

/**
 * "5-minute readings" (v2 Phase 10b Part 1): every 5-minute reading as a table, built like the
 * "Hourly METAR reports" section. The page HTML is the same for everyone and holds no reading;
 * Premium rows load in the browser from the entitled route (shared with the chart: one request).
 */
export const HF_TABLE_FOOTER =
  "Readings as received from NOAA MADIS. Whole-degree Celsius, so converted °F can differ from the station's own reading by 1–2 °F. The official daily high/low is the NWS climate report (CLI).";

const RANGES = [2, 6, 24] as const;
type Range = (typeof RANGES)[number];

const vis = (v: number | null) => (v === null ? "—" : `${v % 1 === 0 ? v.toFixed(0) : Number(v.toFixed(2))} mi`); // prettier-ignore

function wind(r: HfReading): string {
  if (r.wind_kt === null) return "—";
  if (r.wind_kt === 0) return "Calm";
  const dir = r.wind_dir_deg === null ? "—" : `${String(r.wind_dir_deg).padStart(3, "0")}°`;
  return `${dir} ${r.wind_kt} kt${r.gust_kt ? ` G${r.gust_kt}` : ""}`;
}

export function HfReadings({ stationId, tz }: { stationId: string; tz: string }) {
  const { pending, premium } = usePremiumTier();
  const inFeed = inFiveMinuteFeed(stationId);
  const hf = usePremiumData<HfSeriesResponse>(
    `/api/premium/stations/${stationId}/hf?hours=24`,
    premium && inFeed,
  );
  const [range, setRange] = useState<Range>(2);
  const now = useNow(30_000);

  const readings = useMemo(() => hf.data?.readings ?? [], [hf.data]);
  const latest = readings.at(-1) ?? null;
  const staleAfter = hf.data?.stale_after_minutes ?? 30;
  const age = latest && now !== null ? minutesSince(latest.observed_at, now) : null;
  const delayed = age !== null && age > staleAfter;
  const showTable = premium && inFeed && hf.status !== "forbidden";

  return (
    <section
      aria-labelledby="h-hf"
      data-testid="hf-readings"
      className="overflow-hidden rounded-[14px] border border-border bg-surface below-fold"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4">
        <div className="flex flex-col gap-0.5">
          <div className="flex flex-wrap items-center gap-2.5">
            <h2 id="h-hf" className="font-display text-xl font-semibold">
              5-minute readings
            </h2>
            <span className="inline-flex items-center gap-1 rounded-full bg-premium-bg px-2 py-[3px] text-[10px] font-semibold tracking-[.06em] text-premium-text">
              <LockIcon size={10} />
              PREMIUM
            </span>
          </div>
          <span className="text-[12.5px] text-muted-2">
            5-minute ASOS data via NOAA MADIS · not official METAR reports · newest first
          </span>
        </div>
        {showTable && latest ? (
          <div className="flex flex-wrap items-center gap-3">
            <span
              data-testid="hf-latest"
              className={`font-mono text-[12.5px] ${delayed ? "font-semibold text-[#8A4100]" : "text-text-2"}`}
              title="Observed at the station · stored by EdgeFront"
            >
              Latest {formatZulu(latest.observed_at)} · received {formatZulu(latest.ingested_at)}
              {delayed ? " · delayed" : ""}
            </span>
          </div>
        ) : null}
      </div>

      {!inFeed ? (
        <p role="note" className="px-5 py-4 text-[13.5px] text-text-2" data-testid="hf-not-in-feed">
          This station isn&apos;t in the 5-minute feed.
        </p>
      ) : pending ? (
        <div className="p-5">
          <Skeleton className="h-[220px]" label="Loading 5-minute readings" />
        </div>
      ) : !showTable ? (
        <Locked />
      ) : !hf.data ? (
        <div className="p-5">
          {hf.status === "error" ? (
            <UpstreamDown what="The 5-minute data service" />
          ) : (
            <Skeleton className="h-[420px]" label="Loading 5-minute readings" />
          )}
        </div>
      ) : !readings.length ? (
        <div className="p-5">
          <NoData what="5-minute readings">No 5-minute readings in the last 24 hours.</NoData>
        </div>
      ) : (
        <Table readings={readings} range={range} tz={tz} />
      )}

      <div className="flex flex-wrap items-center justify-between gap-2.5 bg-[#F7F8F6] px-5 py-3">
        <span className="text-xs text-muted-2">
          {HF_TABLE_FOOTER}
          {showTable && hf.failed ? " · Connection lost · retrying" : ""}
        </span>
        {showTable && readings.length ? (
          <div className="flex flex-wrap gap-2">
            {RANGES.filter((h) => h !== range).map((h) => (
              <button key={h} type="button" onClick={() => setRange(h)}
                className="min-h-10 cursor-pointer rounded-[8px] border border-[#CFD5D1] bg-surface px-3.5 text-[13px] font-medium text-text-2 hover:border-ink">
                {h === 24 ? "Show all 24 hours" : `Show ${h === 2 ? "last 2" : h} hours`}
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </section>
  );
} // prettier-ignore

/** Free and signed-out: grey placeholder bars only (no numbers, no data), a line, the button. */
function Locked() {
  return (
    <div className="relative flex flex-col gap-3 px-5 py-5" data-testid="hf-locked">
      <div aria-hidden className="flex flex-col gap-2.5">
        {[92, 78, 86, 70, 88, 74].map((w, i) => (
          <div key={i} className="flex gap-3">
            <span className="h-3.5 w-14 rounded bg-[#E7EAE6]" />
            <span className="h-3.5 rounded bg-[#EEF1EE]" style={{ width: `${w}%` }} />
          </div>
        ))}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2.5 rounded-[10px] border border-dashed border-[#D9A35A] bg-[#FFF7EC] px-3.5 py-2.5 text-[13.5px] text-[#6B3A00]">
        <span>Every 5-minute reading for this station, newest first</span>
        <TrialButton />
      </div>
    </div>
  );
}

function Table({ readings, range, tz }: {
  readings: HfReading[];
  range: 2 | 6 | 24;
  tz: string;
}) {
  const items = useMemo(() => tableItems(readings, range, tz), [readings, range, tz]);
  // New rows since the last refresh get a short highlight (none with reduced motion: CSS).
  const seen = useRef<Set<string> | null>(null);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  useEffect(() => {
    const keys = new Set(readings.map((r) => r.observed_at));
    if (seen.current) {
      const added = [...keys].filter((k) => !seen.current!.has(k));
      if (added.length) {
        setFresh(new Set(added));
        const t = setTimeout(() => setFresh(new Set()), 2500);
        seen.current = keys;
        return () => clearTimeout(t);
      }
    }
    seen.current = keys;
  }, [readings]);

  const cols = 10;
  return (
    <div
      className="relative max-h-[70vh] overflow-auto [overflow-anchor:auto] focus-visible:ring-2 focus-visible:ring-brand/50 focus-visible:outline-none"
      tabIndex={0}
      role="region"
      aria-label="5-minute readings table"
    >
      <table className="w-full border-collapse text-[13px] [&_td]:border-b [&_td]:border-hairline [&_td]:px-3 [&_td]:py-2.5 [&_td]:whitespace-nowrap [&_th]:sticky [&_th]:top-0 [&_th]:z-[2] [&_th]:border-b [&_th]:border-border [&_th]:bg-surface [&_th]:px-3 [&_th]:py-2.5 [&_th]:text-left [&_th]:text-[11px] [&_th]:font-semibold [&_th]:tracking-[.04em] [&_th]:whitespace-nowrap [&_th]:text-muted-2 [&_th]:uppercase">
        <caption className="sr-only">
          5-minute readings for the last {range} hours, newest first, with hour dividers and gaps
          marked
        </caption>
        <thead>
            <tr>
              <th scope="col" className="left-0 z-[3] w-[84px]">Time (UTC)</th>
              <th scope="col">Local</th>
              <th scope="col">Wind</th>
              <th scope="col">Visibility</th>
              <th scope="col">Sky</th>
              <th scope="col">Temp °F</th>
              <th scope="col">Exact °F</th>
              <th scope="col">°C</th>
              <th scope="col">Dew °F</th>
              <th scope="col">Altimeter</th>
            </tr>
        </thead>
        <tbody>
          {items.map((it) =>
            it.kind === "hour" ? (
              <tr key={it.key} aria-hidden="false">
                <th scope="rowgroup" colSpan={cols} className="!static !bg-[#F4F6F3] !py-1.5 !text-[11px] !normal-case !tracking-normal text-text-2">
                  {it.label}
                </th>
              </tr>
            ) : it.kind === "gap" ? (
              <tr key={it.key} data-testid="hf-gap">
                <td colSpan={cols} className="!py-1.5 text-[12px] text-muted-2 italic">{it.label}</td>
              </tr>
            ) : (
              <Row key={it.key} r={it.r} tz={tz} fresh={fresh.has(it.r.observed_at)} />
            ),
          )}
        </tbody>
      </table>
    </div>
  );
} // prettier-ignore

const Row = memo(function Row({ r, tz, fresh }: {
  r: HfReading;
  tz: string;
  fresh: boolean;
}) {
  const flagged = !!r.qc_temp && QC_FLAGGED.has(r.qc_temp);
  const dew = r.dewpt_c !== null ? tempFromC(r.dewpt_c, "whole_c") : null;
  const tTip = r.temp ? conversionTooltip(r.temp) : "";
  const dTip = dew ? `Dew point: ${conversionTooltip(dew)}` : "";
  const time = (
    <td className="sticky left-0 z-[1] bg-inherit font-mono font-semibold">
      <span className="inline-flex items-center gap-1.5">
        {formatZulu(r.observed_at)}
        {flagged ? (
          <span
            className="rounded bg-[#FDECEA] px-1 py-px font-sans text-[10px] font-semibold text-[#8E1F14]"
            title={`MADIS quality control: ${r.qc_temp} = ${QC_MEANING[r.qc_temp!] ?? "flagged"}. Left out of the 5-minute high and low.`}
          >
            QC
            <span className="sr-only">
              {` flag ${r.qc_temp}: ${QC_MEANING[r.qc_temp!] ?? "flagged"}, left out of the 5-minute high and low`}
            </span>
          </span>
        ) : null}
      </span>
    </td>
  );
  const rowCls = `bg-surface transition-colors duration-700 ${fresh ? "motion-safe:bg-[#FFF6D8]" : ""}`;
  return (
    <tr className={rowCls} data-testid="hf-row">
      {time}
      <td className="text-muted">{formatLocalTime(r.observed_at, tz)}</td>
      <td className="font-mono">{wind(r)}</td>
      <td>{vis(r.vis_mi)}</td>
      <td>{r.sky ? skyText(r.sky.map((l) => ({ ...l, type: null }))) : "—"}{r.pres_wx ? <span className="ml-1.5 font-mono text-[12px]">{r.pres_wx}</span> : null}</td>
      <td className="font-mono font-semibold" title={tTip}>{r.temp ? r.temp.f_rounded : "—"}{tTip ? <span className="sr-only">{` (${tTip})`}</span> : null}</td>
      <td className="font-mono text-text-2" title={tTip}>{r.temp ? fmtFExact(r.temp) : "—"}</td>
      <td className="font-mono" title={tTip}>{r.temp ? fmtC(r.temp) : r.temp_c !== null ? `${r.temp_c} (off grid)` : "—"}</td>
      <td className="font-mono" title={dTip}>{dew ? dew.f_rounded : "—"}</td>
      <td className="font-mono">{r.altim_inhg !== null ? `${r.altim_inhg.toFixed(2)} inHg` : "—"}</td>
    </tr>
  );
}); // prettier-ignore
