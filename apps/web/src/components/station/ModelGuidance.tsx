"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useNow } from "@/lib/hooks";
import { formatLocalTime, formatZulu } from "@/lib/time";
import type { ModelSeries, ModelsResponse } from "@/lib/types";

import { NoData, Skeleton, UpstreamDown } from "../states";
import {
  CATEGORY_LABEL,
  DEFAULT_STATE,
  GROUPS,
  MODEL_COLOR,
  MODEL_SYMBOL,
  OBSERVED_COLOR,
  type ModelUiState,
  observedData,
  readState,
  runLine,
  SPANS,
  summarize,
  toSeriesData,
  tooltipLines,
  unitLabel,
  VARIABLES,
  writeState,
} from "./models";

type Load = { status: "ok"; data: ModelsResponse } | { status: "loading" } | { status: "failed" };

function Segmented<T extends string>({
  label,
  items,
  value,
  onChange,
}: {
  label: string;
  items: { key: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div role="group" aria-label={label} className="flex rounded-[9px] bg-[#E7EAE6] p-[3px]">
      {items.map((it) => (
        <button
          key={it.key}
          type="button"
          aria-pressed={value === it.key}
          onClick={() => onChange(it.key)}
          className={`min-h-10 cursor-pointer rounded-[7px] px-3 text-[13px] font-medium ${
            value === it.key
              ? "bg-surface text-ink shadow-[0_1px_2px_rgba(16,26,28,.14)]"
              : "text-muted hover:text-ink"
          }`}
        >
          {it.label}
        </button>
      ))}
    </div>
  );
}

function Chip({ m, on, onToggle }: { m: ModelSeries; on: boolean; onToggle: () => void }) {
  const color = MODEL_COLOR[m.colour_token] ?? "#56625F";
  const reasonId = `chip-why-${m.id}`;
  if (!m.available) {
    const short =
      m.reason_code === "no_variable"
        ? (m.reason ?? "no data")
        : m.reason_code === "no_run"
          ? "no run yet"
          : "not available";
    return (
      <span className="group relative inline-flex">
        <button
          type="button"
          aria-disabled="true"
          aria-describedby={reasonId}
          className="inline-flex min-h-10 cursor-not-allowed items-center gap-2 rounded-[8px] border border-dashed border-[#CFD5D1] bg-[#F7F8F6] px-3 text-[13px] font-medium text-muted-2"
        >
          <span
            aria-hidden
            className="size-[9px] rounded-full border"
            style={{ borderColor: color }}
          />
          {m.label}
          <span className="text-[11.5px]">· {short}</span>
        </button>
        <span
          id={reasonId}
          role="tooltip"
          className="pointer-events-none absolute top-full left-0 z-10 mt-1 hidden w-max max-w-[260px] rounded-[6px] border border-border bg-surface px-2.5 py-1.5 text-[12px] text-text-2 shadow-sm group-focus-within:block group-hover:block"
        >
          {m.label}: {m.reason}
        </span>
      </span>
    );
  }
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onToggle}
      className={`inline-flex min-h-10 cursor-pointer items-center gap-2 rounded-[8px] border px-3 text-[13px] font-medium focus-visible:ring-2 focus-visible:ring-brand/50 focus-visible:outline-none ${
        on
          ? "border-ink bg-surface text-ink"
          : "border-[#CFD5D1] bg-[#F7F8F6] text-muted line-through"
      }`}
    >
      <span
        aria-hidden
        className="size-[9px] rounded-full"
        style={{ background: on ? color : "transparent", border: `2px solid ${color}` }}
      />
      {m.label}
      {m.run?.stale ? (
        <span className="text-[11px] font-semibold text-[#6B4600]">stale</span>
      ) : null}
    </button>
  );
}

export function ModelGuidance({
  initial,
  stationId,
  stationName,
  tz,
}: {
  initial: ModelsResponse | null;
  stationId: string;
  stationName: string;
  tz: string;
}) {
  const [ui, setUi] = useState<ModelUiState>(DEFAULT_STATE);
  const [load, setLoad] = useState<Load>(
    initial ? { status: "ok", data: initial } : { status: "loading" },
  );
  const cache = useRef(new Map<string, ModelsResponse>());
  const nowMs = useNow(60_000);

  // URL → state once after mount (the server always renders the default view).
  useEffect(() => {
    const st = readState(window.location.search);
    const t = setTimeout(() => setUi(st), 0);
    return () => clearTimeout(t);
  }, []);

  const fetchView = useCallback(
    async (st: ModelUiState) => {
      const key = `${st.variable}|${st.span}`;
      const hit = cache.current.get(key);
      if (hit) return hit;
      const res = await fetch(
        `/api/stations/${stationId}/models?var=${st.variable}&span=${st.span}`,
        {
          cache: "no-store",
        },
      );
      if (!res.ok) throw new Error(String(res.status));
      const json = (await res.json()) as ModelsResponse;
      cache.current.set(key, json);
      return json;
    },
    [stationId],
  );

  useEffect(() => {
    if (initial) cache.current.set(`temp|today`, initial);
  }, [initial]);

  // Data for the current view; refreshed every 5 min while visible.
  useEffect(() => {
    let cancelled = false;
    const run = async (force: boolean) => {
      if (force) cache.current.delete(`${ui.variable}|${ui.span}`);
      const cached = cache.current.get(`${ui.variable}|${ui.span}`);
      if (cached) {
        if (!cancelled) setLoad({ status: "ok", data: cached });
        return;
      }
      if (!cancelled) setLoad({ status: "loading" });
      try {
        const d = await fetchView(ui);
        if (!cancelled) setLoad({ status: "ok", data: d });
      } catch {
        if (!cancelled) setLoad({ status: "failed" });
      }
    };
    const t = setTimeout(() => void run(false), 0);
    const id = setInterval(() => {
      if (document.visibilityState === "visible") void run(true);
    }, 300_000);
    return () => {
      cancelled = true;
      clearTimeout(t);
      clearInterval(id);
    };
  }, [ui, fetchView]);

  const update = (patch: Partial<ModelUiState>) => {
    const next = { ...ui, ...patch };
    setUi(next);
    const qs = writeState(window.location.search, next);
    window.history.replaceState(
      null,
      "",
      `${window.location.pathname}${qs}${window.location.hash}`,
    );
  };

  const data = load.status === "ok" ? load.data : null;
  const hidden = useMemo(() => new Set(ui.hidden), [ui.hidden]);
  const visible = useMemo(
    () =>
      new Set(
        (data?.models ?? []).filter((m) => m.available && !hidden.has(m.id)).map((m) => m.id),
      ),
    [data, hidden],
  );
  const summary = useMemo(() => (data ? summarize(data, visible, tz) : ""), [data, visible, tz]);
  const anyAvailable = !!data?.models.some((m) => m.available);
  const varLabel = VARIABLES.find((v) => v.key === ui.variable)!.long;

  return (
    <section
      aria-labelledby="h-model"
      className="flex flex-col gap-4 rounded-[14px] border border-border bg-surface px-5 pt-[18px] pb-5"
    >
      <div className="flex max-w-[760px] flex-col gap-1">
        <div className="flex flex-wrap items-center gap-2.5">
          <h2 id="h-model" className="font-display text-xl font-semibold">
            Model guidance for {stationName}
          </h2>
          <span className="rounded-full bg-[#EDE8F6] px-2 py-[3px] text-[10px] font-semibold tracking-[.06em] text-[#4B3488]">
            MODEL DATA
          </span>
        </div>
        <span className="text-[12.5px] text-muted-2">
          Third-party forecast models at the station&apos;s grid point or forecast point, with the
          observed METAR line on top so you can compare. Not EdgeFront forecasts.
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-2.5">
        <Segmented
          label="Variable"
          items={VARIABLES}
          value={ui.variable}
          onChange={(variable) => update({ variable })}
        />
        <Segmented
          label="Forecast window"
          items={SPANS}
          value={ui.span}
          onChange={(span) => update({ span })}
        />
        <span className="inline-flex min-h-10 items-center rounded-[8px] border border-border bg-[#F7F8F6] px-3 text-[13px] font-medium text-text-2">
          Latest run per model
        </span>
      </div>

      {data ? (
        <div className="flex flex-wrap items-end gap-[18px]">
          {GROUPS.map((g) => {
            const ms = data.models.filter((m) => m.group === g.key);
            if (!ms.length) return null;
            return (
              <div
                key={g.key}
                role="group"
                aria-label={`${g.label} models`}
                className="flex flex-col gap-1.5"
              >
                <span className="text-[10.5px] font-semibold tracking-[.08em] text-muted uppercase">
                  {g.label}
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {ms.map((m) => (
                    <Chip
                      key={m.id}
                      m={m}
                      on={!hidden.has(m.id)}
                      onToggle={() => {
                        const h = new Set(hidden);
                        if (h.has(m.id)) h.delete(m.id);
                        else h.add(m.id);
                        update({ hidden: [...h].sort() });
                      }}
                    />
                  ))}
                </div>
              </div>
            );
          })}
          <div className="ml-auto flex gap-1.5">
            <button
              type="button"
              onClick={() => update({ hidden: [] })}
              className="min-h-10 cursor-pointer rounded-[8px] border border-[#CFD5D1] px-3 text-[13px] font-medium"
            >
              All
            </button>
            <button
              type="button"
              onClick={() => update({ hidden: data.models.map((m) => m.id).sort() })}
              className="min-h-10 cursor-pointer rounded-[8px] border border-[#CFD5D1] px-3 text-[13px] font-medium"
            >
              None
            </button>
          </div>
        </div>
      ) : null}

      {load.status === "failed" ? (
        <UpstreamDown what="The EdgeFront API" />
      ) : !data ? (
        <Skeleton className="h-[300px]" label="Loading model guidance" />
      ) : !anyAvailable ? (
        <NoData what="model runs">No model run has been received for this station yet.</NoData>
      ) : (
        <ModelChart data={data} visible={visible} tz={tz} summary={summary} />
      )}

      {data ? (
        <>
          <p className="text-[12.5px] leading-normal text-text-2">
            <span className="font-semibold">Summary: </span>
            {summary}
          </p>
          <ul
            className="flex flex-col gap-1 font-mono text-[12px] text-text-2"
            aria-label="Model runs shown"
          >
            {data.models.map((m) => (
              <li
                key={m.id}
                className={`flex flex-wrap gap-x-2 ${m.run?.stale ? "rounded-[4px] bg-warn-halo px-1 text-[#6B4600]" : ""} ${!m.available ? "text-muted-2" : ""}`}
              >
                <span
                  aria-hidden
                  className="mt-[5px] inline-block size-2 shrink-0 rounded-full"
                  style={{ background: MODEL_COLOR[m.colour_token] }}
                />
                <span className="font-semibold">{m.label}</span>
                <span>{runLine(m, nowMs)}</span>
              </li>
            ))}
          </ul>
          <p className="text-[12px] leading-normal text-muted-2">
            Model output is shown for reference. EdgeFront does not rank, blend or endorse models,
            and does not make its own forecast. Values are plotted only at each model&apos;s own
            valid times, at the nearest land grid point (or the NWS forecast point), without any
            adjustment. Cloud categories are drawn at fixed midpoints; the category is the data:
            GFS-MOS and LAMP at the METAR cover midpoints (CL 0 %, FW 19 %, SC 44 %, BK 75 %, OV 100
            %), PFM at the midpoints of the NWS PFM ranges (CL 0–5 %, FW 5–25 %, SC 25–50 %, B1
            50–69 %, B2 69–87 %, OV 87–100 %). IFS and AIFS: © ECMWF, open data licensed under CC BY
            4.0. Window:{" "}
            {data.window.span === "today"
              ? "the climate day"
              : "48 h from the start of the climate day"}{" "}
            ({formatZulu(data.window.start)}–{formatZulu(data.window.end)},{" "}
            {formatLocalTime(data.window.start, tz)}–{formatLocalTime(data.window.end, tz)} local
            standard time) · {varLabel} in {unitLabel(data.unit)}.
          </p>
        </>
      ) : null}
    </section>
  );
}

// ---------------------------------------------------------------- chart (ECharts, lazy)

function ModelChart({
  data,
  visible,
  tz,
  summary,
}: {
  data: ModelsResponse;
  visible: Set<string>;
  tz: string;
  summary: string;
}) {
  const el = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
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
        charts.LineChart,
        comps.GridComponent,
        comps.TooltipComponent,
        comps.MarkAreaComponent,
        comps.MarkLineComponent,
        renderers.CanvasRenderer,
      ]);
      if (disposed || !el.current) return;
      const c = core.init(el.current, undefined, { renderer: "canvas" });
      chart = c;
      c.setOption(buildModelOption(data, visible, tz));
      window.addEventListener("resize", onResize);
      setReady(true);
    })();
    return () => {
      disposed = true;
      window.removeEventListener("resize", onResize);
      chart?.dispose();
    };
  }, [data, visible, tz]);

  return (
    <div className="relative h-[320px]">
      {!ready ? <Skeleton className="absolute inset-0" label="Loading chart" /> : null}
      <div
        ref={el}
        className="absolute inset-0"
        role="img"
        aria-label={`Model guidance chart. ${summary}`}
      />
    </div>
  );
}

export function buildModelOption(data: ModelsResponse, visible: Set<string>, tz: string) {
  const start = Date.parse(data.window.start);
  const end = Date.parse(data.window.end);
  const now = Date.parse(data.now);
  const unit = unitLabel(data.unit);
  const byName = new Map(data.models.map((m) => [m.label, m]));
  const isPct = data.unit === "pct";
  const series: object[] = [
    {
      type: "line",
      name: "_frame",
      data: [],
      silent: true,
      markArea: {
        silent: true,
        itemStyle: { color: "#F2F4F1" },
        data: now > start ? [[{ xAxis: start }, { xAxis: Math.min(now, end) }]] : [],
      },
      markLine: {
        silent: true,
        symbol: "none",
        lineStyle: { color: OBSERVED_COLOR, type: "dashed", width: 1 },
        label: {
          formatter: `Now ${formatZulu(data.now)}`,
          position: "insideEndTop",
          color: OBSERVED_COLOR,
          fontSize: 11,
          fontWeight: 600,
        },
        data: now >= start && now <= end ? [{ xAxis: now }] : [],
      },
    },
  ];
  for (const m of data.models) {
    if (!m.available || !visible.has(m.id) || !m.points.length) continue;
    const color = MODEL_COLOR[m.colour_token] ?? "#56625F";
    series.push({
      type: "line",
      name: m.label,
      data: toSeriesData(m.points, m.native_step_hours).map(([t, v], k) => ({
        value: [t, v],
        p: v === null ? null : (m.points.find((p) => Date.parse(p.valid_time) === t) ?? null),
        k,
      })),
      step: m.kind === "categorical" ? "middle" : false,
      connectNulls: false,
      showSymbol: true,
      symbol: MODEL_SYMBOL[m.id] ?? "circle",
      symbolSize: 7,
      lineStyle: { color, width: 1.8 },
      itemStyle: { color },
      emphasis: { focus: "series" },
      z: 3,
    });
  }
  if (data.observed.points.length) {
    series.push({
      type: "line",
      name: "Observed (METAR)",
      data: observedData(data.observed.points).map(([t, v]) => ({
        value: [t, v],
        p:
          v === null
            ? null
            : (data.observed.points.find((p) => Date.parse(p.valid_time) === t) ?? null),
      })),
      step: data.variable === "cloud" ? "middle" : false,
      connectNulls: false,
      showSymbol: false,
      lineStyle: { color: OBSERVED_COLOR, width: 3 },
      itemStyle: { color: OBSERVED_COLOR },
      z: 5,
    });
  }
  return {
    animation: false,
    textStyle: { fontFamily: "Inter" },
    grid: { left: 48, right: 30, top: 34, bottom: 44 },
    xAxis: {
      type: "time",
      min: start,
      max: end,
      axisLabel: {
        color: "#56625F",
        fontFamily: "JetBrains Mono",
        fontSize: 11,
        hideOverlap: true,
        formatter: (v: number) =>
          `${formatZulu(new Date(v).toISOString())}\n${formatLocalTime(new Date(v).toISOString(), tz)}`,
      },
      axisLine: { lineStyle: { color: "#DDE1DC" } },
      splitLine: { show: true, lineStyle: { color: "#EEF1EE" } },
    },
    yAxis: {
      type: "value",
      scale: !isPct && data.unit !== "kt",
      min: isPct || data.unit === "kt" ? 0 : undefined,
      max: isPct ? 100 : undefined,
      name: unit,
      nameTextStyle: { color: "#56625F", fontSize: 11 },
      axisLabel: {
        color: "#56625F",
        fontFamily: "JetBrains Mono",
        fontSize: 11,
        formatter: (v: number) => String(Math.round(v)),
      },
      splitLine: { lineStyle: { color: "#E4E8E4" } },
    },
    tooltip: {
      trigger: "item",
      confine: true,
      backgroundColor: "#FFFFFF",
      borderColor: "#DDE1DC",
      textStyle: { color: "#101A1C", fontSize: 12 },
      formatter: (prm: {
        seriesName: string;
        data: { p: ModelsResponse["models"][number]["points"][number] | null };
      }) => {
        const p = prm.data?.p;
        if (!p) return "";
        if (prm.seriesName === "Observed (METAR)") {
          const cat = p.category ? ` ${p.category} (${CATEGORY_LABEL[p.category] ?? ""})` : "";
          return [
            "<b>Observed (METAR)</b>",
            `${formatZulu(p.valid_time)} (${formatLocalTime(p.valid_time, tz)})`,
            p.category
              ? `Sky${cat}`
              : `${Math.round(p.value ?? 0)} ${unit}${p.is_computed ? " (computed)" : ""}`,
          ].join("<br/>");
        }
        const m = byName.get(prm.seriesName);
        if (!m) return "";
        const lines = tooltipLines(m, p, data.unit, tz);
        return [`<b>${lines[0]}</b>`, ...lines.slice(1)].join("<br/>");
      },
    },
    series,
  };
}
