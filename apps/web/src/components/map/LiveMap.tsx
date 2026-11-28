"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import type { Map as MlMap, Marker, StyleSpecification } from "maplibre-gl";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import {
  MAX_BOUNDS,
  OUTLINE_STYLE,
  STYLE_TIMEOUT_MS,
  styleUrl,
  WORKER_URL,
} from "@/lib/map/config";
import { layout } from "@/lib/map/overlap";
import { BINS, binFor, STALE_COLOR } from "@/lib/map/scale";
import {
  accessibleLabel,
  METRIC_LABEL,
  sortStations,
  valueFor,
  VENUE_NAME,
  visibleFor,
  type Metric,
  type VenueKey,
} from "@/lib/map/values";
import { usePremiumData } from "@/lib/premium/client";
import type { MapResponse, MapStation } from "@/lib/premium/types";
import { unroundedLine } from "@/lib/temp";
import { formatLocalTime, formatZulu, relativeAge } from "@/lib/time";
import { useNow } from "@/lib/hooks";

import { UpstreamDown } from "../states";
import { MapSkeletonFill } from "./MapSkeleton";

/**
 * The live station map for Premium members (v2 Phase 10 B5). MapLibre with OpenFreeMap; if the
 * street map fails or isn't up within 8 s it switches to the bundled outline (no outside
 * requests). Markers are real buttons (keyboard, screen readers), the number is always on the
 * marker, close markers are spread apart, and the list on the right has the same data.
 */
const FALLBACK_NOTE = "Street map unavailable · showing a simple outline";
const CONUS: [[number, number], [number, number]] = [
  [-124.8, 24.4],
  [-66.9, 49.4],
];

type Hosts = Map<string, HTMLDivElement>;

const tabCls = (on: boolean) =>
  `min-h-10 cursor-pointer rounded-[7px] px-3 text-[13px] font-medium whitespace-nowrap focus-visible:ring-2 focus-visible:ring-brand/50 focus-visible:outline-none ${
    on ? "bg-surface text-ink shadow-[0_1px_2px_rgba(16,26,28,.14)]" : "text-muted hover:text-ink"
  }`;

function Seg<T extends string>({ label, value, items, onChange }: {
  label: string;
  value: T;
  items: [T, string][];
  onChange: (v: T) => void;
}) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap rounded-[9px] bg-[#E7EAE6] p-[3px]">
      {items.map(([k, t]) => (
        <button key={k} type="button" aria-pressed={value === k} onClick={() => onChange(k)} className={tabCls(value === k)}>
          {t}
        </button>
      ))}
    </div>
  );
} // prettier-ignore

function tzName(tz: string): string {
  const names: Record<string, string> = {
    "America/New_York": "Eastern time",
    "America/Detroit": "Eastern time",
    "America/Kentucky/Louisville": "Eastern time",
    "America/Chicago": "Central time",
    "America/Denver": "Mountain time",
    "America/Phoenix": "Mountain time (no DST)",
    "America/Los_Angeles": "Pacific time",
  };
  return names[tz] ?? tz;
}

export function LiveMap() {
  const pm = usePremiumData<MapResponse>("/api/premium/map", true);
  const [metric, setMetric] = useState<Metric>("now");
  const [venue, setVenue] = useState<VenueKey>("all");
  const [sortBy, setSortBy] = useState<"value" | "id">("value");
  const [selected, setSelected] = useState<string | null>(null);
  const [fallback, setFallback] = useState(false);
  const [hosts, setHosts] = useState<Hosts>(new Map());
  const [ready, setReady] = useState(false);
  const mapEl = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MlMap | null>(null);
  const mlRef = useRef<typeof import("maplibre-gl") | null>(null);
  const markers = useRef(new Map<string, Marker>());
  const clusterMarkers = useRef<Marker[]>([]);
  const widths = useRef(new Map<string, number>());
  const buttons = useRef(new Map<string, HTMLButtonElement | null>());
  const fitted = useRef(false);
  const reduced = useRef(false);
  const now = useNow();

  const stations = useMemo(() => pm.data?.stations ?? [], [pm.data]);
  const byId = useMemo(() => new Map(stations.map((s) => [s.station_id, s])), [stations]);
  const shown = useMemo(() => stations.filter((s) => visibleFor(s, venue)), [stations, venue]);

  // ---- map: created once; the data never reloads it
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const placed = markers.current;
    (async () => {
      const ml = await import("maplibre-gl");
      if (disposed || !mapEl.current) return;
      ml.setWorkerUrl(WORKER_URL);
      mlRef.current = ml;
      reduced.current = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      const coarse = window.matchMedia("(pointer: coarse)").matches;
      const narrow = window.matchMedia("(max-width: 639px)").matches;
      const map = new ml.Map({
        container: mapEl.current,
        style: styleUrl(),
        bounds: CONUS,
        fitBoundsOptions: { padding: 28 },
        maxBounds: MAX_BOUNDS,
        attributionControl: { compact: narrow },
        cooperativeGestures: coarse,
        fadeDuration: reduced.current ? 0 : 300,
        dragRotate: false,
        pitchWithRotate: false,
        touchPitch: false,
      });
      map.touchZoomRotate.disableRotation();
      map.addControl(new ml.NavigationControl({ showCompass: false }), "top-right");
      mapRef.current = map;
      let usingFallback = false;
      let settled = false;
      const toFallback = () => {
        if (usingFallback || disposed) return;
        usingFallback = true;
        setFallback(true);
        map.setStyle(OUTLINE_STYLE as unknown as StyleSpecification);
      };
      timer = setTimeout(() => {
        if (!settled) toFallback();
      }, STYLE_TIMEOUT_MS);
      map.once("idle", () => {
        settled = true;
        if (timer) clearTimeout(timer);
      });
      map.on("error", () => toFallback()); // style, tile or glyph request failed
      map.on("load", () => setReady(true));
      // Phones: the compact attribution starts collapsed (its (i) button opens it, by touch or
      // keyboard) so it doesn't cover the markers; on wider screens it is always shown in full.
      const collapse = () => {
        if (!narrow) return;
        mapEl.current
          ?.querySelectorAll(".maplibregl-ctrl-attrib.maplibregl-compact-show")
          .forEach((e) => e.classList.remove("maplibregl-compact-show"));
      };
      map.once("idle", collapse);
      map.on("styledata", () => setReady(true));
      const ro = new ResizeObserver(() => map.resize());
      ro.observe(mapEl.current);
      map.once("remove", () => ro.disconnect());
    })();
    return () => {
      disposed = true;
      if (timer) clearTimeout(timer);
      placed.forEach((m) => m.remove());
      placed.clear();
      clusterMarkers.current.forEach((m) => m.remove());
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, []);

  // ---- markers: one host element per station, added once; React renders into them
  useEffect(() => {
    const map = mapRef.current;
    const ml = mlRef.current;
    if (!map || !ml || !ready || !stations.length) return;
    let added = false;
    const west = stations.filter((s) => s.lat !== null && s.lon !== null).sort((a, b) => a.lon! - b.lon!);
    for (const st of west) {
      if (markers.current.has(st.station_id)) continue;
      const host = document.createElement("div");
      host.dataset.station = st.station_id;
      const m = new ml.Marker({ element: host, anchor: "center" }).setLngLat([st.lon!, st.lat!]).addTo(map);
      markers.current.set(st.station_id, m);
      added = true;
    }
    if (added) {
      setHosts(new Map([...markers.current].map(([id, m]) => [id, m.getElement() as HTMLDivElement])));
    }
    if (!fitted.current && west.length) {
      fitted.current = true;
      const lons = west.map((s) => s.lon!);
      const lats = west.map((s) => s.lat!);
      const small = (mapEl.current?.clientWidth ?? 800) < 640;
      map.fitBounds(
        [[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]],
        { padding: small ? 18 : 48, duration: 0 },
      );
    }
  }, [ready, stations]); // prettier-ignore

  // ---- overlaps: spread small groups, cluster big ones (zoomed far out), at the current zoom
  const relayout = useCallback(() => {
    const map = mapRef.current;
    const ml = mlRef.current;
    if (!map || !ml) return;
    const pts = [];
    for (const [id, m] of markers.current) {
      const st = byId.get(id);
      const el = m.getElement();
      const shown = !!st && visibleFor(st, venue);
      if (!shown) {
        el.style.display = "none";
        continue;
      }
      el.style.display = "";
      const w = (el.firstElementChild as HTMLElement | null)?.offsetWidth || widths.current.get(id) || 34;
      widths.current.set(id, w);
      const p = map.project(m.getLngLat());
      pts.push({ id, x: p.x, y: p.y, w });
    }
    const { offsets, clusters } = layout(pts);
    for (const [id, off] of offsets) markers.current.get(id)?.setOffset(off);
    clusterMarkers.current.forEach((m) => m.remove());
    clusterMarkers.current = clusters.map((c) => {
      for (const id of c.ids) markers.current.get(id)!.getElement().style.display = "none";
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "ef-cluster";
      btn.dataset.testid = "map-cluster";
      btn.textContent = `${c.ids.length}`;
      btn.setAttribute("aria-label", `${c.ids.length} stations here: ${c.ids.join(", ")}. Zoom in to see them.`);
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const ll = c.ids.map((id) => markers.current.get(id)!.getLngLat());
        const lons = ll.map((x) => x.lng);
        const lats = ll.map((x) => x.lat);
        const before = map.getZoom();
        map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: 70, duration: 0, maxZoom: 11 });
        if (map.getZoom() - before < 0.5) map.jumpTo({ center: map.unproject([c.x, c.y]), zoom: before + 1.5 });
      });
      return new ml.Marker({ element: btn, anchor: "center" }).setLngLat(map.unproject([c.x, c.y])).addTo(map);
    });
  }, [byId, venue]); // prettier-ignore

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    relayout();
    map.on("zoomend", relayout);
    map.on("resize", relayout);
    return () => {
      map.off("zoomend", relayout);
      map.off("resize", relayout);
    };
  }, [relayout, hosts, metric, pm.data]);

  useEffect(() => {
    for (const [id, m] of markers.current) m.getElement().style.zIndex = id === selected ? "5" : "2";
  }, [selected, hosts]);

  const select = useCallback((id: string | null) => {
    setSelected(id);
    const map = mapRef.current;
    const m = id ? markers.current.get(id) : null;
    if (!map || !m) return;
    const b = map.getBounds();
    if (!b.contains(m.getLngLat())) map.panTo(m.getLngLat(), { duration: 0 }); // never animated
  }, []);

  const closePanel = useCallback(() => {
    const id = selected;
    setSelected(null);
    if (id) buttons.current.get(id)?.focus();
  }, [selected]);

  useEffect(() => {
    if (!selected) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closePanel();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [selected, closePanel]);

  // ---- header text
  const total = stations.length;
  const notIn = stations.filter((s) => !s.in_feed).map((s) => s.station_id);
  const latestObs = stations
    .map((s) => s.hf_latest?.observed_at)
    .filter((x): x is string => !!x)
    .sort()
    .at(-1);
  const sel = selected ? byId.get(selected) ?? null : null;

  if (!pm.data && pm.status === "error") {
    return (
      <div className="flex flex-col gap-4">
        <h1 className="font-display text-[32px] font-bold tracking-[-0.02em]">Live station map</h1>
        <UpstreamDown what="The 5-minute data service" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4" data-testid="live-map" data-fallback={fallback || undefined}>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h1 className="font-display text-[32px] font-bold tracking-[-0.02em]">Live station map</h1>
          <p className="text-sm text-muted" data-testid="map-header">
            {total
              ? notIn.length
                ? `5-minute ASOS data for ${total - notIn.length} of ${total} settlement stations (${notIn.join(" and ")}: hourly METAR, not in the 5-minute feed)`
                : `5-minute ASOS data for all ${total} settlement stations`
              : "5-minute ASOS data"}
            {latestObs ? ` · latest readings ${formatZulu(latestObs)}` : ""}
            {pm.updatedAt ? `, updated ${formatZulu(new Date(pm.updatedAt).toISOString())}` : ""}
            {pm.failed ? " · Connection lost · retrying" : ""}
          </p>
        </div>
        <div className="flex flex-wrap gap-2.5">
          <Seg label="Show" value={metric} onChange={setMetric}
            items={[["now", "Now"], ["high", "High so far"], ["low", "Low so far"]]} />
          <Seg label="Venue" value={venue} onChange={(v) => { setVenue(v); setSelected(null); }}
            items={[["all", "All"], ["kalshi", "Kalshi"], ["polymarket", "Polymarket"], ["robinhood", "Robinhood"]]} />
        </div>
      </div>

      <div className="flex flex-wrap items-start gap-4">
        <section aria-label="Map" className="flex min-w-0 flex-[999_1_720px] flex-col gap-2.5 rounded-[16px] border border-border bg-surface p-3">
          <div className="relative w-full overflow-hidden rounded-[10px] bg-[#EAF1F4]">
            <div ref={mapEl} className="aspect-[4/3] max-h-[70vh] w-full sm:aspect-[1000/600]" data-testid="map-canvas" />
            {!pm.data ? (
              <div className="absolute inset-0 z-[4]">
                <MapSkeletonFill />
              </div>
            ) : null}
            {sel ? <Panel st={sel} metric={metric} now={now} onClose={closePanel} /> : null}
          </div>
          <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11.5px] text-text-2" data-testid="map-legend">
              <span className="font-semibold">°F</span>
              {BINS.map((b) => (
                <span key={b.label} className="inline-flex items-center gap-1">
                  <span aria-hidden className="size-3 rounded-[3px]" style={{ background: b.color }} />
                  {b.label}
                </span>
              ))}
              <span className="inline-flex items-center gap-1">
                <span aria-hidden className="size-3 rounded-[3px]" style={{ background: STALE_COLOR }} />
                delayed
              </span>
              <span className="inline-flex items-center gap-1">
                <span aria-hidden className="size-3 rounded-[3px] border-2 border-[#0A6E69] bg-white" />
                METAR
              </span>
          </div>
          {fallback ? (
            <p role="status" className="text-[12.5px] font-semibold text-[#6B4600]" data-testid="map-fallback">
              {FALLBACK_NOTE}
            </p>
          ) : null}
          <p className="text-[12px] text-muted-2">
            Marker colour = the selected value; the number is always shown. Select a marker (click,
            or Tab then Enter) for details. Hollow markers with METAR: station not in the 5-minute
            feed, hourly METAR shown. Grey: 5-minute data delayed.
          </p>
        </section>

        <aside aria-labelledby="h-list" className="flex min-w-0 flex-[1_1_300px] flex-col overflow-hidden rounded-[16px] border border-border bg-surface">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-3">
            <h2 id="h-list" className="font-display text-base font-semibold">
              {metric === "high" ? "Highest so far" : metric === "low" ? "Lowest so far" : "Current temperature"}
              <span className="ml-2 text-[12px] font-normal text-muted-2">{shown.length} stations</span>
            </h2>
            <Seg label="Sort the list" value={sortBy} onChange={setSortBy} items={[["value", "Value"], ["id", "Station ID"]]} />
          </div>
          <ol className="max-h-[560px] overflow-y-auto" data-testid="map-list">
            {sortStations(shown, metric, sortBy).map((st) => {
              const v = valueFor(st, metric);
              const on = st.station_id === selected;
              return (
                <li key={st.station_id}>
                  <button
                    type="button"
                    aria-pressed={on}
                    aria-label={accessibleLabel(st, metric)}
                    onClick={() => select(on ? null : st.station_id)}
                    className={`flex w-full cursor-pointer items-center gap-2.5 border-b border-hairline px-4 py-2.5 text-left focus-visible:ring-2 focus-visible:ring-brand/50 focus-visible:outline-none focus-visible:ring-inset ${on ? "bg-[#E6F2F1]" : "bg-surface hover:bg-[#F7FAF9]"}`}
                  >
                    <span className="w-12 font-mono text-[13px] font-semibold">{st.station_id}</span>
                    <span className="min-w-0 flex-1 truncate text-[12.5px] text-[#3A4644]">{st.name}</span>
                    {v.source === "metar" ? <span className="rounded-[4px] bg-[#EEF1EE] px-1 text-[9.5px] font-semibold text-text-2">METAR</span> : null}
                    {v.stale ? <span className="text-[11px] text-[#6B4600]">delayed</span> : null}
                    <span className="font-mono text-[14px] font-semibold" style={{ color: v.temp ? (v.stale ? STALE_COLOR : binFor(v.temp.f_rounded).color) : undefined }}>
                      {v.temp ? `${v.temp.f_rounded}°` : "—"}
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
        </aside>
      </div>

      {[...hosts].map(([id, host]) => {
        const st = byId.get(id);
        if (!st) return null;
        return createPortal(
          <MarkerButton
            st={st}
            metric={metric}
            on={id === selected}
            refFn={(el) => buttons.current.set(id, el)}
            onClick={() => select(id === selected ? null : id)}
          />,
          host,
          id,
        );
      })}
    </div>
  );
} // prettier-ignore

function MarkerButton({ st, metric, on, refFn, onClick }: {
  st: MapStation;
  metric: Metric;
  on: boolean;
  refFn: (el: HTMLButtonElement | null) => void;
  onClick: () => void;
}) {
  const v = valueFor(st, metric);
  const color = v.temp ? binFor(v.temp.f_rounded).color : "#56625F";
  const hollow = v.source === "metar";
  const bg = hollow ? "#FFFFFF" : v.stale ? STALE_COLOR : color;
  const label = accessibleLabel(st, metric) + (v.stale ? " (delayed)" : "");
  return (
    <button
      ref={refFn}
      type="button"
      aria-label={label}
      aria-pressed={on}
      data-testid={`marker-${st.station_id}`}
      data-kind={hollow ? "metar" : v.stale ? "stale" : "5min"}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      className="flex h-[26px] min-w-[34px] cursor-pointer items-center justify-center gap-1 rounded-[13px] px-1.5 font-mono text-[12.5px] font-bold shadow-[0_1px_4px_rgba(16,26,28,.3)] focus-visible:ring-4 focus-visible:ring-[#101A1C]/60 focus-visible:outline-none"
      style={{
        background: bg,
        color: hollow ? "#101A1C" : "#FFFFFF",
        border: on ? "3px solid #101A1C" : hollow ? `2px solid ${color}` : "2px solid #FFFFFF",
      }}
    >
      {v.temp ? v.temp.f_rounded : "—"}
      {hollow ? <span className="rounded-[3px] bg-[#EEF1EE] px-[3px] font-sans text-[8.5px] font-semibold text-[#2A3533]">METAR</span> : null}
    </button>
  );
} // prettier-ignore

function Panel({ st, metric, now, onClose }: {
  st: MapStation;
  metric: Metric;
  now: number | null;
  onClose: () => void;
}) {
  const vals = (["now", "high", "low"] as Metric[]).map((m) => ({ m, v: valueFor(st, m) }));
  const qc = st.in_feed ? st.hf_so_far.excluded_qc_count : 0;
  const latest = st.hf_latest?.observed_at;
  return (
    <div
      role="dialog"
      aria-modal="false"
      aria-labelledby="map-panel-title"
      data-testid="map-panel"
      className="relative z-[6] m-2 flex flex-col gap-1.5 rounded-[12px] border border-border bg-surface px-3.5 py-3 shadow-[0_8px_24px_rgba(16,26,28,.16)] sm:absolute sm:top-3 sm:left-3 sm:m-0 sm:w-[300px]"
    >
      <div className="flex items-baseline justify-between gap-2">
        <span id="map-panel-title" className="font-mono text-[15px] font-bold text-brand">{st.station_id}</span>
        <span className="text-[11.5px] text-muted-2">{tzName(st.tz)}</span>
        <button type="button" onClick={onClose} aria-label="Close station details" className="ml-auto inline-flex size-8 cursor-pointer items-center justify-center rounded-[6px] text-muted hover:bg-[#EEF1EE] focus-visible:ring-2 focus-visible:ring-brand/50 focus-visible:outline-none">
          ✕
        </button>
      </div>
      <span className="text-[13px] text-text-2">{st.name}</span>
      <div className="mt-1 flex flex-col gap-1.5">
        {vals.map(({ m, v }) => (
          <div key={m} className={`flex flex-col rounded-[8px] px-2 py-1 ${m === metric ? "bg-[#F1F4F1]" : ""}`}>
            <span className="flex items-baseline justify-between gap-2">
              <span className={`text-[11.5px] ${m === "high" ? "text-[#8A3A0E]" : m === "low" ? "text-[#1D4F8A]" : "text-muted-2"}`}>
                {m === "now" ? "Now" : m === "high" ? "High so far" : "Low so far"}
                {v.source === "metar" ? " · METAR" : ""}
              </span>
              <span className="font-mono text-[18px] font-semibold">{v.temp ? `${v.temp.f_rounded}°` : "—"}</span>
            </span>
            {v.temp ? <span className="font-mono text-[11px] text-text-2">{unroundedLine(v.temp)}</span> : null}
            {v.at ? <span className="text-[10.5px] text-muted-2">at {formatZulu(v.at)} ({formatLocalTime(v.at, st.tz)})</span> : null}
          </div>
        ))}
      </div>
      {qc ? <span className="text-[11.5px] text-[#6B4600]">{qc} reading{qc > 1 ? "s" : ""} excluded (QC)</span> : null}
      <span className="text-[11.5px] text-muted-2">
        {st.in_feed
          ? latest
            ? `Latest 5-min reading ${formatZulu(latest)}${now !== null ? ` · ${relativeAge(latest, now)}` : ""}${st.status !== "ok" ? " · delayed" : ""}`
            : "No recent 5-minute reading"
          : "Not in the 5-minute feed: hourly METAR values"}
        {" · "}
        {st.venues.map((v) => VENUE_NAME[v]).join(", ") || "no venue"}
      </span>
      <Link href={`/station/${st.station_id}`} className="mt-1 inline-flex min-h-9 items-center justify-center rounded-[10px] bg-brand px-3 text-[13px] font-semibold text-white no-underline hover:bg-brand-hover hover:text-white">
        Open station
      </Link>
      <span className="sr-only">{METRIC_LABEL[metric]}</span>
    </div>
  );
} // prettier-ignore
