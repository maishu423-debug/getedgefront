"use client";

import { Fragment, useState } from "react";

import { formatLocalWithZone, formatShortDate, formatZulu, hhmmTo12h } from "@/lib/time";
import type { DailySummariesResponse, DailySummaryRow } from "@/lib/types";
import { fmtMphWind, fmtPrecip } from "@/lib/units";

import { UpstreamDown } from "../states";

const COVERS: Record<string, string> = {
  so_far: "so far, partial day",
  preliminary: "preliminary, partial day",
  final: "final",
};

function issuerLabel(r: DailySummaryRow, stationId: string): string {
  if (r.product === "DSM") return `ASOS · ${stationId}${r.issuer ? ` (via ${r.issuer})` : ""}`;
  return r.issuer ? `NWS office ${r.issuer}` : "National Weather Service";
}

export function DailySummaries({
  data,
  stationId,
  failed,
}: {
  data: DailySummariesResponse | null;
  stationId: string;
  failed: boolean;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const tz = data?.tz ?? "UTC";
  const iem = data?.rows.some((r) => r.status === "ok" && r.source === "iem") ?? false;

  return (
    <section
      aria-labelledby="h-daily"
      className="overflow-hidden rounded-[14px] border border-border bg-surface below-fold"
    >
      <div className="flex flex-wrap items-center justify-between gap-2.5 border-b border-border px-5 py-4">
        <div className="flex flex-col gap-0.5">
          <h2 id="h-daily" className="font-display text-xl font-semibold">
            Daily summaries
          </h2>
          <span className="text-[12.5px] text-muted-2">
            Official NWS products for this station · climate day runs midnight to midnight local
            standard time
          </span>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <span className="rounded-full bg-brand-tint px-2.5 py-1 font-semibold text-brand-hover">
            CLI · Daily Climate Report
          </span>
          <span className="rounded-full bg-[#EEF1EE] px-2.5 py-1 font-semibold text-text-2">
            DSM · ASOS Daily Summary
          </span>
        </div>
      </div>

      {failed || data === null ? (
        <div className="p-5">
          <UpstreamDown what="The EdgeFront API" />
        </div>
      ) : data.status === "none_available" ? (
        <div className="p-5">
          <div
            role="status"
            className="rounded-[10px] border border-border bg-[#FAFBF9] px-4 py-3 text-sm text-text-2"
          >
            <p className="font-semibold">
              {data.message ?? "No daily summary available for this station"}
            </p>
            <p className="mt-1 text-[13px] leading-relaxed">
              The NWS does not currently publish a Daily Climate Report (CLI) or an ASOS Daily
              Summary (DSM) for {stationId}. The hourly METARs below are the observations available
              for this station.
            </p>
          </div>
        </div>
      ) : (
        <div
          className="relative overflow-x-auto focus-visible:ring-2 focus-visible:ring-brand/50 focus-visible:outline-none"
          tabIndex={0}
          role="region"
          aria-label="Daily summaries table"
        >
          <table className="w-full border-collapse text-[13px] [&_td]:border-b [&_td]:border-hairline [&_td]:px-3 [&_td]:py-2.5 [&_td]:whitespace-nowrap [&_th]:border-b [&_th]:border-border [&_th]:px-3 [&_th]:py-2.5 [&_th]:text-[11px] [&_th]:font-semibold [&_th]:tracking-[.04em] [&_th]:whitespace-nowrap [&_th]:text-muted-2 [&_th]:uppercase">
            <caption className="sr-only">
              Daily climate reports and ASOS daily summaries for today and yesterday
            </caption>
            <thead>
              <tr>
                <th scope="col" className="text-left">
                  Product
                </th>
                <th scope="col" className="text-left">
                  Covers
                </th>
                <th scope="col" className="text-left">
                  Issued
                </th>
                <th scope="col" className="text-right">
                  Max
                </th>
                <th scope="col" className="text-right">
                  Min
                </th>
                <th scope="col" className="text-right">
                  Precip
                </th>
                <th scope="col" className="text-right">
                  Normal hi / lo
                </th>
                <th scope="col">
                  <span className="sr-only">Product text</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r) => {
                const key = `${r.product}-${r.day}`;
                const isOpen = open === key;
                const has = r.status === "ok";
                return (
                  <Fragment key={key}>
                    <tr className={has ? "" : "bg-[#FAFBF9]"}>
                      <td>
                        <div className="flex flex-col gap-0.5">
                          <span
                            className={`font-mono text-[12.5px] font-semibold ${r.product === "CLI" ? "text-brand-hover" : "text-text-2"}`}
                          >
                            {r.product}
                            {r.is_correction ? (
                              <span className="ml-1.5 rounded bg-premium-bg px-1 text-[10.5px] text-premium-text">
                                COR
                              </span>
                            ) : null}
                          </span>
                          <span className="text-[11.5px] text-muted-2">
                            {issuerLabel(r, stationId)}
                          </span>
                        </div>
                      </td>
                      <td>
                        <div className="flex flex-col gap-0.5">
                          <span className="font-semibold">
                            {r.day === "today" ? "Today" : "Yesterday"},{" "}
                            {formatShortDate(r.covers.date)}
                          </span>
                          <span className="text-[11.5px] text-muted-2">
                            {has && r.covers.kind
                              ? COVERS[r.covers.kind]
                              : r.status === "not_available"
                                ? "—"
                                : "not issued yet"}
                            {has && r.valid_as_of_local
                              ? ` · as of ${hhmmTo12h(r.valid_as_of_local)}`
                              : ""}
                          </span>
                        </div>
                      </td>
                      {has ? (
                        <>
                          <td>
                            <div className="flex flex-col gap-0.5">
                              <span className="font-mono">{formatZulu(r.issued_at)}</span>
                              <span className="text-[11.5px] text-muted-2">
                                {formatLocalWithZone(r.issued_at, tz)}
                              </span>
                            </div>
                          </td>
                          <td className="text-right">
                            <div className="flex flex-col items-end gap-0.5">
                              <span className="font-mono text-base font-semibold text-high">
                                {r.max_f !== null ? `${r.max_f}°F` : "—"}
                              </span>
                              <span className="text-[11.5px] text-muted-2">
                                {r.max_time_local ? `at ${hhmmTo12h(r.max_time_local)}` : ""}
                              </span>
                            </div>
                          </td>
                          <td className="text-right">
                            <div className="flex flex-col items-end gap-0.5">
                              <span className="font-mono text-base font-semibold text-dewpt">
                                {r.min_f !== null ? `${r.min_f}°F` : "—"}
                              </span>
                              <span className="text-[11.5px] text-muted-2">
                                {r.min_time_local ? `at ${hhmmTo12h(r.min_time_local)}` : ""}
                              </span>
                            </div>
                          </td>
                          <td className="text-right font-mono">
                            {fmtPrecip(r.precip_in, r.precip_trace)}
                          </td>
                          <td className="text-right font-mono text-muted">
                            {r.product === "CLI" &&
                            (r.normal_high_f !== null || r.normal_low_f !== null)
                              ? `${r.normal_high_f ?? "—"}° / ${r.normal_low_f ?? "—"}°`
                              : "—"}
                          </td>
                          <td className="text-right">
                            <button
                              type="button"
                              aria-expanded={isOpen}
                              aria-controls={`raw-${key}`}
                              onClick={() => setOpen(isOpen ? null : key)}
                              className="min-h-10 cursor-pointer rounded-[8px] border border-[#CFD5D1] bg-surface px-3.5 text-[13px] font-medium text-text-2 hover:border-ink"
                            >
                              {isOpen ? "Hide text" : "Product text"}
                            </button>
                          </td>
                        </>
                      ) : (
                        <td colSpan={6} className="text-[13px] !whitespace-normal text-muted-2">
                          {r.reason ?? "Not available."}
                        </td>
                      )}
                    </tr>
                    {has && isOpen ? (
                      <tr id={`raw-${key}`}>
                        <td colSpan={8} className="bg-[#F7F8F6] !whitespace-normal">
                          {r.peak_gust || r.peak_wind ? (
                            <p className="mb-2 text-[12.5px] text-text-2">
                              Highest wind{" "}
                              {fmtMphWind(
                                r.peak_wind?.dir_deg ?? null,
                                r.peak_wind?.speed_mph ?? null,
                              )}
                              {r.peak_wind?.time_local
                                ? ` at ${hhmmTo12h(r.peak_wind.time_local)}`
                                : ""}{" "}
                              · highest gust{" "}
                              {fmtMphWind(
                                r.peak_gust?.dir_deg ?? null,
                                r.peak_gust?.speed_mph ?? null,
                              )}
                              {r.peak_gust?.time_local
                                ? ` at ${hhmmTo12h(r.peak_gust.time_local)}`
                                : ""}{" "}
                              (decoded from the DSM; times are local standard time)
                            </p>
                          ) : null}
                          {r.issuances_for_day > 1 ? (
                            <p className="mb-2 text-[12px] text-muted-2">
                              {r.issuances_for_day} issuances received for this day; the latest{" "}
                              {r.covers.kind === "final" ? "final" : ""} one is shown.
                            </p>
                          ) : null}
                          {r.decode_errors.length ? (
                            <p className="mb-2 text-[12px] text-[#8A4100]">
                              Some fields could not be decoded: {r.decode_errors.join("; ")}. The
                              product text below is exactly as received.
                            </p>
                          ) : null}
                          <pre className="max-h-96 overflow-auto border-l-[3px] border-border py-1.5 pl-3 font-mono text-[12.5px] leading-normal whitespace-pre text-[#2A3533]">
                            {r.raw_text}
                          </pre>
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <div className="border-t border-hairline px-5 py-2.5 text-xs leading-normal text-muted-2">
        Shown as published by the NWS. CLI and DSM max/min come from the ASOS sensor, including
        peaks between hourly reports, so they can differ from the METAR high above. Some markets
        name one of these products as their settlement source. Check each market&apos;s rules. If a
        product isn&apos;t published for a station, its row says so. Times in the products are local
        standard time; wind in mph.
        {iem ? <> DSM via Iowa Environmental Mesonet, Iowa State University.</> : null}
      </div>
    </section>
  );
}
