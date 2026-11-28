"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { breakAtGaps } from "@/lib/gaps";
import { inFiveMinuteFeed, NOT_IN_FEED_NOTE } from "@/lib/coverage";
import { useNearViewport } from "@/lib/hooks";
import { usePremiumData, usePremiumTier } from "@/lib/premium/client";
import type { HfSeriesResponse } from "@/lib/premium/types";
import { fmtFExact } from "@/lib/temp";
import { formatLocalTime, formatZulu } from "@/lib/time";
import type { ObservedResponse } from "@/lib/types";
import { COVER_RANK, cToFDisplay, fmtMetarWind } from "@/lib/units";

import { TrialButton } from "../billing/TrialButton";
import { LockIcon } from "../Chrome";
import { NoData, Skeleton } from "../states";
import { prepare, summarize } from "./observed";
import { HF_GAP_MIN, hfTooltip, prepareHf, summarizeHf, type PreparedHf } from "./observedHf";

type Mode = "5min" | "metar";

type PanelKey = "temp" | "rh" | "wind" | "sky" | "pres";
const PANELS: { key: PanelKey; label: string; color: string; height: number }[] = [
  { key: "temp", label: "Temp & dew point", color: "#C24E12", height: 200 },
  { key: "rh", label: "Humidity (computed)", color: "#6B4FA0", height: 110 },
  { key: "wind", label: "Wind", color: "#0A6E69", height: 110 },
  { key: "sky", label: "Sky", color: "#5F7488", height: 34 },
  { key: "pres", label: "Pressure", color: "#3D4A47", height: 110 },
];
const SKY_COLORS: Record<string, [string, string]> = {
  CLR: ["#EEF1EF", "#33424F"], SKC: ["#EEF1EF", "#33424F"], FEW: ["#D5DEE6", "#22303B"],
  SCT: ["#A9BBCB", "#101A1C"], BKN: ["#5F7488", "#FFFFFF"], OVC: ["#33424F", "#FFFFFF"], VV: ["#33424F", "#FFFFFF"],
}; // prettier-ignore
const MISSING = "#F1ECE2";

function ToggleButton({
  on,
  onClick,
  color,
  children,
}: {
  on: boolean;
  onClick: () => void;
  color?: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className={`inline-flex min-h-10 cursor-pointer items-center rounded-[8px] border px-3.5 text-[13px] font-medium whitespace-nowrap focus-visible:ring-2 focus-visible:ring-brand/50 focus-visible:outline-none ${
        on ? "border-ink bg-ink text-white" : "border-[#CFD5D1] bg-surface text-text-2"
      }`}
    >
      {color ? (
        <span
          aria-hidden
          className="mr-2 inline-block size-2.5 rounded-[3px]"
          style={{ background: color }}
        />
      ) : null}
      {children}
    </button>
  );
}

/** Fixed teaser copy: never computed from live Premium data (owner B3). */
export const CHART_TEASER = "5-minute readings catch peaks and dips between hourly reports.";

export function ObservedChart({ data, tz }: { data: ObservedResponse; tz: string }) {
  const { premium } = usePremiumTier();
  const inFeed = inFiveMinuteFeed(data.station_id); // registry: KNYC and KBKF are not
  const hf = usePremiumData<HfSeriesResponse>(
    `/api/premium/stations/${data.station_id}/hf?hours=24`,
    premium && inFeed,
  );
  const [chosen, setChosen] = useState<Mode | null>(null);
  const mode: Mode = premium && inFeed && hf.status !== "forbidden" ? (chosen ?? "5min") : "metar";
  const [hours, setHours] = useState<6 | 24>(24);
  const [on, setOn] = useState<Record<PanelKey, boolean>>({
    temp: true,
    rh: true,
    wind: true,
    sky: true,
    pres: false,
  });
  const [ready, setReady] = useState(false);
  const el = useRef<HTMLDivElement>(null);
  // Watch the section, not the chart box: the box only exists once there is data to draw (the
  // 5-minute view shows a skeleton first), and the hook observes the element it sees at mount.
  const box = useRef<HTMLElement>(null);
  const near = useNearViewport(box);
  const prep = useMemo(() => prepare(data, hours), [data, hours]);
  const hfPrep = useMemo(
    () => (mode === "5min" && hf.data ? prepareHf(hf.data, data, hours) : null),
    [mode, hf.data, data, hours],
  );
  const summary = useMemo(
    () => (hfPrep ? summarizeHf(hfPrep, hours, tz) : summarize(prep, hours, tz)),
    [hfPrep, prep, hours, tz],
  );
  const active = PANELS.filter((p) => on[p.key]);
  const height = active.reduce((h, p) => h + p.height + 36, 44);
  const latest = prep.points.at(-1);
  const latestHf = hfPrep?.points.at(-1);
  const hfLoading = mode === "5min" && !hfPrep;
  const empty = hfPrep ? !hfPrep.points.length : !prep.points.length;

  useEffect(() => {
    if (!near) return; // ECharts loads only when the chart is near the viewport
    let disposed = false;
    let chart: { dispose: () => void; resize: () => void } | null = null;
    const onResize = () => chart?.resize();
    (async () => {
      const [core, charts, comps, renderers] = await Promise.all([
        import("echarts/core"),
        import("echarts/charts"),
        import("echarts/components"),
        import("echarts/renderers"),
      ]);
      core.use([
        charts.LineChart, charts.ScatterChart, charts.CustomChart,
        comps.GridComponent, comps.TooltipComponent, comps.MarkAreaComponent, comps.AxisPointerComponent,
        renderers.CanvasRenderer,
      ]); // prettier-ignore
      if (disposed || !el.current) return;
      const c = core.init(el.current, undefined, { renderer: "canvas" });
      chart = c;
      c.setOption(buildOption(prep, active, tz, hfPrep));
      window.addEventListener("resize", onResize);
      setReady(true);
    })();
    return () => {
      disposed = true;
      window.removeEventListener("resize", onResize);
      chart?.dispose();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prep, hfPrep, on, tz, near]);

  return (
    <section
      ref={box}
      aria-labelledby="h-chart"
      className="flex flex-col gap-4 rounded-[14px] border border-border bg-surface px-5 pt-[18px] pb-5 below-fold"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-col gap-0.5">
          <h2 id="h-chart" className="font-display text-xl font-semibold">
            Observed conditions
          </h2>
          <span className="text-[12.5px] text-muted-2">
            {mode === "5min"
              ? "5-minute ASOS readings with the hourly METAR reports marked · gaps are left empty"
              : "Hourly METAR reports, including SPECI · missing reports are left empty, never filled in"}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          <div
            role="group"
            aria-label="Data resolution"
            className="flex rounded-[9px] bg-[#E7EAE6] p-[3px]"
          >
            {premium && inFeed ? (
              <SegButton on={mode === "5min"} onClick={() => setChosen("5min")}>
                5-minute
              </SegButton>
            ) : !inFeed ? (
              <button
                type="button"
                aria-disabled="true"
                aria-describedby="chart-not-in-feed"
                className="inline-flex min-h-10 cursor-not-allowed items-center gap-1.5 rounded-[7px] px-3 text-[13px] font-medium text-muted"
              >
                {premium ? null : <LockIcon size={12} />}
                5-minute{premium ? "" : " · Premium"}
              </button>
            ) : (
              <button
                type="button"
                aria-disabled="true"
                aria-describedby="chart-teaser"
                className="inline-flex min-h-10 cursor-not-allowed items-center gap-1.5 rounded-[7px] px-3 text-[13px] font-medium text-premium-text"
              >
                <LockIcon size={12} />
                5-minute · Premium
              </button>
            )}
            <SegButton on={mode === "metar"} onClick={() => setChosen("metar")}>
              Hourly METAR
            </SegButton>
          </div>
          <div
            role="group"
            aria-label="Time range"
            className="flex rounded-[9px] bg-[#E7EAE6] p-[3px]"
          >
            {([6, 24] as const).map((h) => (
              <button
                key={h}
                type="button"
                aria-pressed={hours === h}
                onClick={() => setHours(h)}
                className={`min-h-10 cursor-pointer rounded-[7px] px-3 text-[13px] font-medium ${
                  hours === h
                    ? "bg-surface text-ink shadow-[0_1px_2px_rgba(16,26,28,.14)]"
                    : "text-muted hover:text-ink"
                }`}
              >
                {h} h
              </button>
            ))}
          </div>
        </div>
      </div>

      <div role="group" aria-label="Chart panels" className="flex flex-wrap gap-2">
        {PANELS.map((p) => (
          <ToggleButton
            key={p.key}
            on={on[p.key]}
            color={p.color}
            onClick={() => setOn((o) => ({ ...o, [p.key]: !o[p.key] }))}
          >
            {p.label}
          </ToggleButton>
        ))}
      </div>

      {!inFeed ? (
        <p
          id="chart-not-in-feed"
          role="note"
          className="rounded-[10px] border border-[#CFE3E1] bg-[#E6F2F1] px-3.5 py-2.5 text-[13.5px] text-[#064F4B]"
        >
          {NOT_IN_FEED_NOTE} Premium shows the same hourly METAR here.
        </p>
      ) : !premium ? (
        <div
          id="chart-teaser"
          className="flex flex-wrap items-center justify-between gap-2.5 rounded-[10px] border border-dashed border-[#D9A35A] bg-[#FFF7EC] px-3.5 py-2.5 text-[13.5px] text-[#6B3A00]"
        >
          <span>{CHART_TEASER}</span>
          <TrialButton />
        </div>
      ) : null}

      {latestHf ? (
        <div className="flex flex-wrap gap-x-[22px] gap-y-1.5 rounded-[8px] bg-[#F7F8F6] px-3 py-2.5 font-mono text-[12.5px] text-text-2">
          <span className="font-semibold">
            Latest 5-minute {formatZulu(latestHf.observed_at)} (
            {formatLocalTime(latestHf.observed_at, tz)})
          </span>
          <span>
            Temp{" "}
            {latestHf.temp
              ? `${latestHf.temp.f_rounded}°F (${fmtFExact(latestHf.temp)} unrounded)`
              : "—"}
          </span>
          <span>Dew pt {latestHf.dewF !== null ? `${latestHf.dewF.toFixed(1)}°F` : "—"}</span>
          <span>RH {latestHf.rh !== null ? `${latestHf.rh}% (computed)` : "—"}</span>
          <span>
            Wind{" "}
            {latestHf.wind_kt === null
              ? "—"
              : `${latestHf.wind_dir_deg ?? "—"}° ${latestHf.wind_kt} kt${latestHf.gust_kt ? ` G${latestHf.gust_kt}` : ""}`}
          </span>
          <span>
            Altim {latestHf.altim_inhg !== null ? `${latestHf.altim_inhg.toFixed(2)} inHg` : "—"}
          </span>
        </div>
      ) : latest && mode === "metar" ? (
        <div className="flex flex-wrap gap-x-[22px] gap-y-1.5 rounded-[8px] bg-[#F7F8F6] px-3 py-2.5 font-mono text-[12.5px] text-text-2">
          <span className="font-semibold">
            Latest {latest.report_type} {formatZulu(latest.observed_at)} (
            {formatLocalTime(latest.observed_at, tz)})
          </span>
          <span>Temp {latest.temp_f !== null ? `${latest.temp_f}°F` : "—"}</span>
          <span>Dew pt {latest.dewpt_f !== null ? `${latest.dewpt_f}°F` : "—"}</span>
          <span>
            RH {latest.rh_computed !== null ? `${Math.round(latest.rh_computed)}% (computed)` : "—"}
          </span>
          <span>
            Wind{" "}
            {fmtMetarWind(latest.wind_dir_deg, latest.wind_vrb, latest.wind_kt, latest.gust_kt)}
          </span>
          <span>
            Altim {latest.altim_inhg !== null ? `${latest.altim_inhg.toFixed(2)} inHg` : "—"}
          </span>
        </div>
      ) : null}

      {hfLoading ? (
        <Skeleton className="h-[420px]" label="Loading 5-minute readings" />
      ) : empty ? (
        mode === "5min" ? (
          <NoData what="5-minute readings">
            No 5-minute readings in the last {hours} hours
            {hf.data && !hf.data.in_feed ? " (this station isn't in the 5-minute feed)" : ""}.
          </NoData>
        ) : (
          <NoData what="METAR reports">No METAR reports in the last {hours} hours.</NoData>
        )
      ) : active.length === 0 ? (
        <p className="text-sm text-muted">Turn on a panel above to see the chart.</p>
      ) : (
        <div className="relative" style={{ height }}>
          {!ready ? <Skeleton className="absolute inset-0" label="Loading chart" /> : null}
          <div
            ref={el}
            className="absolute inset-0"
            role="img"
            aria-label={`Observed conditions chart. ${summary}`}
          />
        </div>
      )}

      {mode === "5min" && hfPrep?.points.length ? (
        <div className="flex flex-wrap gap-3.5 text-[11.5px] text-muted">
          <span className="flex items-center gap-1.5">
            <span aria-hidden className="h-[3px] w-3.5 bg-[#C24E12]" />
            Temperature (5-min, unrounded)
          </span>
          <span className="flex items-center gap-1.5">
            <span aria-hidden className="h-[3px] w-3.5 bg-[#1F5FA8]" />
            Dew point
          </span>
          <span className="flex items-center gap-1.5">
            <span aria-hidden className="size-[7px] rounded-full bg-ink" />
            Hourly METAR
          </span>
          {hf.failed ? <span className="text-[#8A4100]">Connection lost · retrying</span> : null}
          {!hf.failed && hf.updatedAt ? (
            <span className="font-mono">
              Updated {formatZulu(new Date(hf.updatedAt).toISOString())}
            </span>
          ) : null}
        </div>
      ) : null}

      {on.sky && prep.points.length ? (
        <div className="flex flex-wrap gap-3.5 text-[11.5px] text-muted">
          <span className="font-semibold">Sky cover</span>
          {[
            ["CLR", "Clear"],
            ["FEW", "Few"],
            ["SCT", "Scattered"],
            ["BKN", "Broken"],
            ["OVC", "Overcast"],
          ].map(([k, t]) => (
            <span key={k} className="flex items-center gap-1.5">
              <span
                className="size-3 rounded-[3px] border border-[#CFD5D1]"
                style={{ background: SKY_COLORS[k!]![0] }}
              />
              {t}
            </span>
          ))}
          <span className="flex items-center gap-1.5">
            <span
              className="size-3 rounded-[3px] border border-[#E8DCC4]"
              style={{ background: MISSING }}
            />
            No reports
          </span>
        </div>
      ) : null}
      <p className="text-[12.5px] leading-normal text-text-2">
        <span className="font-semibold">Summary: </span>
        {summary} Wind in knots. Relative humidity is computed from temperature and dew point
        {mode === "5min" ? " (whole °C in the 5-minute data, so it moves in steps)" : ""}.
      </p>
    </section>
  );
}

function SegButton({ on, onClick, children }: {
  on: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className={`min-h-10 cursor-pointer rounded-[7px] px-3 text-[13px] font-medium ${
        on ? "bg-surface text-ink shadow-[0_1px_2px_rgba(16,26,28,.14)]" : "text-muted hover:text-ink"
      }`}
    >
      {children}
    </button>
  );
} // prettier-ignore

// ---------------------------------------------------------------- ECharts option

type Prep = ReturnType<typeof prepare>;

function buildOption(p: Prep, panels: typeof PANELS, tz: string, hf: PreparedHf | null = null) {
  const grids: object[] = [];
  const xAxes: object[] = [];
  const yAxes: object[] = [];
  const series: object[] = [];
  let top = 18;
  const win = hf ?? p;
  const gapAreas = win.gaps.map((g) => [{ xAxis: g.startMs }, { xAxis: g.endMs }]);
  const gapMin = hf ? HF_GAP_MIN : 90;

  panels.forEach((panel, i) => {
    const last = i === panels.length - 1;
    grids.push({ left: 56, right: 16, top, height: panel.height });
    xAxes.push({
      type: "time", gridIndex: i, min: win.startMs, max: win.endMs,
      axisLabel: last
        ? { show: true, color: "#56625F", fontFamily: "JetBrains Mono", fontSize: 11, hideOverlap: true,
            formatter: (v: number) => `${formatZulu(new Date(v).toISOString())}\n${formatLocalTime(new Date(v).toISOString(), tz)}` }
        : { show: false },
      axisTick: { show: last }, axisLine: { lineStyle: { color: "#DDE1DC" } },
      splitLine: { show: true, lineStyle: { color: "#EEF1EE" } },
    }); // prettier-ignore
    const name = { temp: "°F", rh: "% RH*", wind: "kt", sky: "", pres: "inHg" }[panel.key];
    yAxes.push({
      type: "value", gridIndex: i, scale: panel.key !== "rh" && panel.key !== "wind", name,
      nameLocation: "end", nameGap: 6, nameTextStyle: { color: "#56625F", fontSize: 11, align: "right", padding: [0, 4, 0, 0] },
      min: panel.key === "rh" ? 0 : panel.key === "wind" ? 0 : panel.key === "sky" ? 0 : undefined,
      max: panel.key === "rh" ? 100 : panel.key === "sky" ? 1 : undefined,
      show: panel.key !== "sky", splitNumber: panel.key === "temp" ? 4 : 2,
      axisLabel: { color: "#56625F", fontFamily: "JetBrains Mono", fontSize: 11,
        formatter: (v: number) => (panel.key === "pres" ? v.toFixed(2) : String(Math.round(v))) },
      splitLine: { lineStyle: { color: "#E4E8E4" } },
    }); // prettier-ignore

    // gap shading for this panel (on an empty helper series)
    series.push({
      type: "line", xAxisIndex: i, yAxisIndex: i, data: [], silent: true,
      markArea: { silent: true, itemStyle: { color: MISSING },
        label: { show: i === 0, position: "insideTop", color: "#7A5A1E", fontSize: 11, fontWeight: 600, formatter: hf ? "No readings" : "No reports" },
        data: gapAreas },
    }); // prettier-ignore

    const line = (key: string, color: string, vals: { t: number; v: number | null }[], width = 2) => ({
      type: "line", name: key, xAxisIndex: i, yAxisIndex: i, data: breakAtGaps(vals, gapMin),
      connectNulls: false, showSymbol: !hf, symbolSize: 4, lineStyle: { color, width }, itemStyle: { color },
      emphasis: { disabled: true },
    }); // prettier-ignore

    if (panel.key === "temp" && hf) {
      series.push(
        line(
          "Temperature (5-min)",
          "#C24E12",
          hf.points.map((x) => ({ t: x.t, v: x.tempF })),
          2,
        ),
      );
      series.push(
        line(
          "Dew point",
          "#1F5FA8",
          hf.points.map((x) => ({ t: x.t, v: x.dewF })),
        ),
      );
      series.push({
        type: "scatter",
        name: "Hourly METAR",
        xAxisIndex: i,
        yAxisIndex: i,
        symbolSize: 7,
        silent: true,
        itemStyle: { color: "#101A1C", borderColor: "#FFFFFF", borderWidth: 1 },
        z: 5,
        data: hf.metar.map((m) => [m.t, m.tempF]),
      });
    } else if (panel.key === "rh" && hf) {
      series.push(
        line(
          "RH (computed)",
          "#6B4FA0",
          hf.points.map((x) => ({ t: x.t, v: x.rh })),
        ),
      );
    } else if (panel.key === "pres" && hf) {
      series.push(
        line(
          "Altimeter",
          "#3D4A47",
          hf.points.map((x) => ({ t: x.t, v: x.altim_inhg })),
        ),
      );
    } else if (panel.key === "wind" && hf) {
      series.push(
        line(
          "Wind",
          "#0A6E69",
          hf.points.map((x) => ({ t: x.t, v: x.wind_kt })),
        ),
      );
      series.push({
        type: "scatter",
        name: "Gust",
        xAxisIndex: i,
        yAxisIndex: i,
        symbolSize: 5,
        silent: true,
        itemStyle: { color: "#7FB8B4" },
        data: hf.points.filter((x) => x.gust_kt !== null).map((x) => [x.t, x.gust_kt]),
      });
    } else if (panel.key === "temp") {
      series.push(
        line(
          "Temperature",
          "#C24E12",
          p.points.map((x) => ({ t: x.t, v: cToFDisplay(x.temp_c) })),
          2.4,
        ),
      );
      series.push(
        line(
          "Dew point",
          "#1F5FA8",
          p.points.map((x) => ({ t: x.t, v: cToFDisplay(x.dewpt_c) })),
        ),
      );
    } else if (panel.key === "rh") {
      series.push(
        line(
          "RH (computed)",
          "#6B4FA0",
          p.points.map((x) => ({ t: x.t, v: x.rh_computed })),
        ),
      );
    } else if (panel.key === "pres") {
      series.push(
        line(
          "Altimeter",
          "#3D4A47",
          p.points.map((x) => ({ t: x.t, v: x.altim_inhg })),
        ),
      );
    } else if (panel.key === "wind") {
      series.push(
        line(
          "Wind",
          "#0A6E69",
          p.points.map((x) => ({ t: x.t, v: x.wind_kt })),
        ),
      );
      series.push({
        type: "custom", name: "Gust", xAxisIndex: i, yAxisIndex: i, silent: true,
        data: p.points.filter((x) => x.gust_kt !== null).map((x) => [x.t, x.wind_kt ?? 0, x.gust_kt]),
        renderItem: (_params: unknown, api: { value: (n: number) => number; coord: (v: number[]) => number[] }) => {
          const a = api.coord([api.value(0), api.value(1)]);
          const b = api.coord([api.value(0), api.value(2)]);
          return { type: "line", shape: { x1: a[0], y1: a[1], x2: b[0], y2: b[1] }, style: { stroke: "#7FB8B4", lineWidth: 3 } };
        },
      }); // prettier-ignore
    } else if (panel.key === "sky") {
      const blocks = p.points.map((x, k) => {
        const next = p.points[k + 1]?.t ?? p.endMs;
        const end = Math.min(next, x.t + 90 * 60_000, p.endMs);
        const cover = x.sky_cover ?? "";
        return [x.t, end, COVER_RANK[cover] ?? -1, cover];
      });
      series.push({
        type: "custom", name: "Sky", xAxisIndex: i, yAxisIndex: i, silent: true, data: blocks,
        renderItem: (_params: unknown, api: { value: (n: number) => number | string; coord: (v: number[]) => number[]; size: (v: number[]) => number[] }) => {
          const s = api.coord([api.value(0) as number, 1]);
          const e = api.coord([api.value(1) as number, 0]);
          const cover = String(api.value(3));
          const [bg, fg] = SKY_COLORS[cover] ?? [MISSING, "#7A5A1E"];
          return {
            type: "group",
            children: [
              { type: "rect", shape: { x: s[0], y: s[1], width: Math.max(1, e[0]! - s[0]!), height: e[1]! - s[1]! }, style: { fill: bg, stroke: "#FFFFFF" } },
              ...(e[0]! - s[0]! > 26 ? [{ type: "text", style: { text: cover || "—", x: s[0]! + 4, y: s[1]! + 11, fill: fg, font: "600 10px JetBrains Mono" } }] : []),
            ],
          };
        },
      }); // prettier-ignore
    }
    top += panel.height + 36;
  });

  const nearest = (t: number) => {
    let best = p.points[0];
    for (const x of p.points) if (Math.abs(x.t - t) < Math.abs((best?.t ?? 0) - t)) best = x;
    return best && Math.abs(best.t - t) <= 45 * 60_000 ? best : null;
  };

  return {
    animation: false,
    textStyle: { fontFamily: "Inter" },
    grid: grids,
    xAxis: xAxes,
    yAxis: yAxes,
    series,
    axisPointer: { link: [{ xAxisIndex: "all" }], lineStyle: { color: "#101A1C", type: "dashed" } },
    tooltip: {
      trigger: "axis", confine: true, backgroundColor: "#FFFFFF", borderColor: "#DDE1DC",
      textStyle: { color: "#101A1C", fontSize: 12 },
      formatter: (params: { axisValue: number }[]) => {
        if (hf) {
          const t = params[0]?.axisValue ?? 0;
          let best: (typeof hf.points)[number] | null = null;
          for (const x of hf.points) if (!best || Math.abs(x.t - t) < Math.abs(best.t - t)) best = x;
          if (!best || Math.abs(best.t - t) > 7.5 * 60_000) return "No 5-minute reading at this time";
          const b = best;
          const m = hf.metar.find((d) => Math.abs(d.t - b.t) <= 150_000);
          return [...hfTooltip(b, tz), ...(m ? [`Hourly ${m.report_type} ${formatZulu(m.observed_at)}: ${m.tempF.toFixed(2)} °F unrounded`] : [])].join("<br/>");
        }
        const x = nearest(params[0]?.axisValue ?? 0);
        if (!x) return "No report at this time";
        const rows = [
          `<b>${x.report_type} ${formatZulu(x.observed_at)}</b> (${formatLocalTime(x.observed_at, tz)})`,
          `Temp ${x.temp_f ?? "—"}°F · Dew pt ${x.dewpt_f ?? "—"}°F`,
          `RH ${x.rh_computed !== null ? Math.round(x.rh_computed) + "% (computed)" : "—"}`,
          `Wind ${fmtMetarWind(x.wind_dir_deg, x.wind_vrb, x.wind_kt, x.gust_kt)}`,
          `Sky ${x.sky.map((l) => `${l.cover}${l.base_ft !== null ? " " + l.base_ft.toLocaleString("en-US") + " ft" : ""}`).join(", ") || "—"}`,
          `Altimeter ${x.altim_inhg !== null ? x.altim_inhg.toFixed(2) + " inHg" : "—"}`,
        ];
        return rows.join("<br/>");
      },
    }, // prettier-ignore
  };
}
