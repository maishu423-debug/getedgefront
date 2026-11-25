"use client";

import { useState } from "react";

import { formatLocalTime, formatZulu } from "@/lib/time";
import type { MetarOut, MetarsResponse } from "@/lib/types";
import { fmtMetarWind, skyText } from "@/lib/units";

import { NoData, UpstreamDown } from "../states";

function TypeTag({ m }: { m: MetarOut }) {
  return (
    <span className="inline-flex flex-wrap gap-1">
      <span
        className={
          m.report_type === "SPECI"
            ? "rounded bg-premium-bg px-1.5 py-px font-bold text-premium-text"
            : "font-bold text-brand"
        }
      >
        {m.report_type}
      </span>
      {m.is_correction ? (
        <span
          className="rounded bg-badge-bg px-1.5 py-px text-[11px] font-semibold text-badge-text"
          title="Correction"
        >
          COR
        </span>
      ) : null}
      {m.superseded ? (
        <span className="rounded bg-[#EEF1EE] px-1.5 py-px text-[11px] font-semibold text-muted">
          replaced by COR
        </span>
      ) : null}
    </span>
  );
}

const vis = (v: number | null) => (v === null ? "—" : `${v % 1 === 0 ? v.toFixed(0) : v} mi`);

export function MetarReports({
  data,
  tz,
  failed,
}: {
  data: MetarsResponse | null;
  tz: string;
  failed: boolean;
}) {
  const [view, setView] = useState<"raw" | "dec">("raw");
  const [all, setAll] = useState(false);
  const reports = data?.reports ?? [];
  const newest = reports[0] ? Date.parse(reports[0].observed_at) : 0;
  const shown = all
    ? reports
    : reports.filter((m) => newest - Date.parse(m.observed_at) <= 12 * 3600_000);
  const hasCor = reports.some((m) => m.is_correction);

  return (
    <section
      aria-labelledby="h-metar"
      className="overflow-hidden rounded-[14px] border border-border bg-surface"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4">
        <div className="flex flex-col gap-0.5">
          <h2 id="h-metar" className="font-display text-xl font-semibold">
            Hourly METAR reports
          </h2>
          <span className="text-[12.5px] text-muted-2">
            Routine reports at the station&apos;s scheduled minute, plus SPECI special reports ·
            newest first
          </span>
        </div>
        <div
          role="group"
          aria-label="METAR view"
          className="flex rounded-[9px] bg-[#E7EAE6] p-[3px]"
        >
          {(
            [
              ["raw", "Raw"],
              ["dec", "Decoded"],
            ] as const
          ).map(([k, t]) => (
            <button
              key={k}
              type="button"
              aria-pressed={view === k}
              onClick={() => setView(k)}
              className={`min-h-10 cursor-pointer rounded-[7px] px-3 text-[13px] font-medium ${
                view === k
                  ? "bg-surface text-ink shadow-[0_1px_2px_rgba(16,26,28,.14)]"
                  : "text-muted hover:text-ink"
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {failed || data === null ? (
        <div className="p-5">
          <UpstreamDown what="The EdgeFront API" />
        </div>
      ) : reports.length === 0 ? (
        <div className="p-5">
          <NoData what="METAR reports" />
        </div>
      ) : view === "raw" ? (
        <ol className="m-0 list-none p-0">
          {shown.map((m) => (
            <li
              key={m.report_id}
              className={`grid grid-cols-[84px_minmax(0,1fr)] items-baseline gap-4 border-b border-hairline px-5 py-2.5 sm:grid-cols-[96px_minmax(0,1fr)] ${
                m.superseded ? "opacity-60" : ""
              }`}
            >
              <div className="flex flex-col gap-0.5">
                <span className="font-mono text-[13px] font-semibold">
                  {formatZulu(m.observed_at)}
                </span>
                <span className="text-[11.5px] text-muted-2">
                  {formatLocalTime(m.observed_at, tz)}
                </span>
              </div>
              <div className="flex flex-col gap-1">
                <TypeTag m={m} />
                <code className="font-mono text-[13px] leading-[1.55] [overflow-wrap:anywhere] text-ink">
                  {m.raw_text}
                </code>
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <div className="relative overflow-x-auto">
          <table className="w-full border-collapse text-[13px] [&_td]:border-b [&_td]:border-hairline [&_td]:px-3 [&_td]:py-2.5 [&_td]:whitespace-nowrap [&_th]:border-b [&_th]:border-border [&_th]:px-3 [&_th]:py-2.5 [&_th]:text-left [&_th]:text-[11px] [&_th]:font-semibold [&_th]:tracking-[.04em] [&_th]:whitespace-nowrap [&_th]:text-muted-2 [&_th]:uppercase">
            <caption className="sr-only">Decoded METAR reports, newest first</caption>
            <thead>
              <tr>
                <th scope="col">Time (UTC)</th>
                <th scope="col">Local</th>
                <th scope="col">Type</th>
                <th scope="col">Wind</th>
                <th scope="col">Visibility</th>
                <th scope="col">Sky</th>
                <th scope="col">Temp / Dew °F</th>
                <th scope="col">Altimeter</th>
                <th scope="col">SLP</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((m) => (
                <tr key={m.report_id} className={m.superseded ? "opacity-60" : ""}>
                  <td className="font-mono font-semibold">{formatZulu(m.observed_at)}</td>
                  <td className="text-muted">{formatLocalTime(m.observed_at, tz)}</td>
                  <td>
                    <TypeTag m={m} />
                  </td>
                  <td className="font-mono">
                    {fmtMetarWind(m.wind_dir_deg, m.wind_vrb, m.wind_kt, m.gust_kt)}
                  </td>
                  <td>{vis(m.vis_mi)}</td>
                  <td>{skyText(m.sky)}</td>
                  <td className="font-mono">
                    {m.temp_f ?? "—"} / {m.dewpt_f ?? "—"}
                    {m.temp_precision === "whole" ? (
                      <span className="ml-1 text-[11px] text-muted-2">(whole °C)</span>
                    ) : null}
                  </td>
                  <td className="font-mono">
                    {m.altim_inhg !== null ? `${m.altim_inhg.toFixed(2)} inHg` : "—"}
                  </td>
                  <td className="font-mono">
                    {m.slp_hpa !== null ? `${m.slp_hpa.toFixed(1)} hPa` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="flex flex-wrap items-center justify-between gap-2.5 bg-[#F7F8F6] px-5 py-3">
        <span className="text-xs text-muted-2">
          Reports exactly as transmitted. Decoded view is EdgeFront&apos;s reading of the same text;
          wind in knots.
          {hasCor
            ? " COR = corrected report; it replaces the earlier report for the same time."
            : ""}
        </span>
        {reports.length > shown.length || all ? (
          <button
            type="button"
            onClick={() => setAll((a) => !a)}
            className="min-h-10 cursor-pointer rounded-[8px] border border-[#CFD5D1] bg-surface px-3.5 text-[13px] font-medium text-text-2 hover:border-ink"
          >
            {all ? "Show last 12 hours" : "Show all 24 hours"}
          </button>
        ) : null}
      </div>
    </section>
  );
}
