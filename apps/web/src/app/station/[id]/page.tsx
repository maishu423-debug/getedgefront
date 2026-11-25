import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { PageShell } from "@/components/Chrome";
import { CurrentCards } from "@/components/station/CurrentCards";
import { DailySummaries } from "@/components/station/DailySummaries";
import { ForecastCard } from "@/components/station/ForecastCard";
import { MetarReports } from "@/components/station/MetarReports";
import { ModelGuidance } from "@/components/station/ModelGuidance";
import { ObservedChart } from "@/components/station/ObservedChart";
import { StationSearch } from "@/components/StationSearch";
import { NoData, Skeleton, UpstreamDown } from "@/components/states";
import {
  getCurrent,
  getDaily,
  getForecast,
  getMetars,
  getModels,
  getObserved,
  getStation,
  getStations,
} from "@/lib/api";
import registry from "@/generated/stations.json";
import { apiInternalUrl } from "@/lib/api";
import { SITE_URL } from "@/lib/site";
import { formatLocalWithZone } from "@/lib/time";
import type { StationMeta } from "@/lib/types";

const ID = /^K[A-Z0-9]{3}$/;
const REGISTRY = registry.stations;
const KNOWN = new Set(REGISTRY.map((s) => s.id));

export async function generateMetadata({ params }: PageProps<"/station/[id]">): Promise<Metadata> {
  const { id } = await params;
  const sid = id.toUpperCase();
  const res = ID.test(sid) ? await getStation(sid) : null;
  if (!res || !res.ok) return { title: "Station not found", robots: { index: false } };
  const st = res.data.station;
  const title = `${st.id} ${st.name} — live METAR, daily high, NWS forecast`;
  const description = `Observed temperature, today's high so far, NWS daily climate report and ASOS daily summary, and the NWS forecast for ${st.id} (${st.name}), each with its source and time stamp.`;
  const url = `${SITE_URL}/station/${st.id}`;
  return {
    title,
    description,
    alternates: { canonical: url },
    openGraph: { title: `${title} | EdgeFront`, description, url, type: "website" },
  };
}

/** Every registry station is prerendered. API first (2 s); if the build can't reach it, the
 * list copied from data/stations.yaml at build time (scripts/gen-stations.mjs). */
export async function generateStaticParams(): Promise<{ id: string }[]> {
  try {
    const res = await fetch(`${apiInternalUrl()}/api/v1/stations`, {
      signal: AbortSignal.timeout(2000),
    });
    if (res.ok) {
      const body = (await res.json()) as { stations: { id: string }[] };
      if (body.stations.length) return body.stations.map((s) => ({ id: s.id }));
    }
  } catch {
    // fall through to the registry copy
  }
  return REGISTRY.map((s) => ({ id: s.id }));
}

/**
 * Unknown ids are rejected here, before any Suspense boundary streams, so the response is a
 * real HTTP 404 (owner Q21/A4). Known ids are checked against the build-time registry copy;
 * `dynamicParams = false` is not available with Cache Components.
 */
export default async function StationPage({ params }: PageProps<"/station/[id]">) {
  const { id } = await params;
  if (!KNOWN.has(id)) notFound();
  return (
    <PageShell active="stations" iem ecmwf>
      <Suspense fallback={<StationSkeleton />}>
        <StationContent params={params} />
      </Suspense>
    </PageShell>
  );
}

function StationSkeleton() {
  return (
    <main
      id="main"
      className="mx-auto flex w-full max-w-(--container-content) flex-col gap-6 px-4 pt-7 pb-14 sm:px-8"
    >
      <Skeleton className="h-14 w-72" label="Loading station" />
      <div className="flex flex-wrap gap-6">
        <Skeleton className="h-[240px] flex-[999_1_560px]" />
        <Skeleton className="h-[420px] flex-[1_1_340px]" />
      </div>
      <Skeleton className="h-[260px]" />
      <Skeleton className="h-[520px]" />
    </main>
  );
}

function fmtLatLon(lat: number | null, lon: number | null): string {
  if (lat === null || lon === null) return "position unknown";
  return `${Math.abs(lat).toFixed(3)}°${lat >= 0 ? "N" : "S"} ${Math.abs(lon).toFixed(3)}°${lon >= 0 ? "E" : "W"}`;
}

function utcOffsetLabel(min: number): string {
  const h = Math.abs(min) / 60;
  return `UTC${min < 0 ? "−" : "+"}${Number.isInteger(h) ? h : h.toFixed(1)}`;
}

function Title({ st }: { st: StationMeta }) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-wrap items-baseline gap-x-3.5 gap-y-1">
        <h1 className="font-display text-[40px] font-bold tracking-[-0.03em] sm:text-[46px]">
          {st.id}
        </h1>
        <span className="text-[19px] font-medium">{st.name}</span>
      </div>
      <div className="flex flex-wrap gap-x-[18px] gap-y-1.5 font-mono text-[12.5px] text-muted">
        {st.official_name ? <span>{st.official_name}</span> : null}
        <span>{fmtLatLon(st.lat, st.lon)}</span>
        {st.elevation_m !== null ? <span>Elev {Math.round(st.elevation_m)} m</span> : null}
        <span>ASOS</span>
        <span>
          Local standard time {utcOffsetLabel(st.std_utc_offset_minutes)} · {st.tz}
        </span>
        <span>Local time {formatLocalWithZone(st.local_time, st.tz)}</span>
      </div>
      {st.venues.length ? (
        <p className="text-[12.5px] text-muted-2">
          Used by:{" "}
          {[...new Set(st.venues.map((v) => v.venue[0]!.toUpperCase() + v.venue.slice(1)))].join(
            ", ",
          )}{" "}
          {st.venues_verified
            ? ""
            : "· venue labels are being verified against each market's rules"}
        </p>
      ) : null}
    </div>
  );
}

async function StationContent({ params }: { params: PageProps<"/station/[id]">["params"] }) {
  const { id } = await params;
  const sid = id.toUpperCase();
  if (!ID.test(sid)) notFound();
  const stRes = await getStation(sid);
  if (!stRes.ok && stRes.notFound) notFound();
  if (!stRes.ok) {
    return (
      <main
        id="main"
        className="mx-auto w-full max-w-(--container-content) px-4 pt-7 pb-14 sm:px-8"
      >
        <h1 className="mb-4 font-display text-[40px] font-bold">{sid}</h1>
        <UpstreamDown what="The EdgeFront API" />
      </main>
    );
  }
  const st = stRes.data.station;
  const [cur, fc, daily, obs, metars, all, models] = await Promise.all([
    getCurrent(sid),
    getForecast(sid),
    getDaily(sid),
    getObserved(sid),
    getMetars(sid),
    getStations(),
    getModels(sid),
  ]);
  const searchList = all.ok
    ? all.data.stations.map(({ id: i, name, city, state, aliases }) => ({
        id: i,
        name,
        city,
        state,
        aliases,
      }))
    : [];

  return (
    <main
      id="main"
      className="mx-auto flex w-full max-w-(--container-content) flex-col gap-6 px-4 pt-7 pb-14 sm:px-8"
    >
      <StationSearch stations={searchList} size="sm" />
      <div className="flex flex-wrap items-stretch gap-6">
        <section
          aria-label="Current conditions"
          className="flex min-w-0 flex-[999_1_560px] flex-col gap-5"
        >
          <Title st={st} />
          {cur.ok ? (
            <CurrentCards initial={cur.data} tz={st.tz} />
          ) : (
            <UpstreamDown what="The EdgeFront API" />
          )}
        </section>
        <ForecastCard fc={fc.ok ? fc.data : null} tz={st.tz} failed={!fc.ok} />
      </div>

      <DailySummaries data={daily.ok ? daily.data : null} stationId={sid} failed={!daily.ok} />

      {obs.ok ? (
        <ObservedChart data={obs.data} tz={st.tz} />
      ) : (
        <section className="rounded-[14px] border border-border bg-surface p-5">
          <h2 className="mb-3 font-display text-xl font-semibold">Observed conditions</h2>
          {obs.notFound ? (
            <NoData what="METAR reports" />
          ) : (
            <UpstreamDown what="The EdgeFront API" />
          )}
        </section>
      )}

      <MetarReports data={metars.ok ? metars.data : null} tz={st.tz} failed={!metars.ok} />
      <ModelGuidance
        initial={models.ok ? models.data : null}
        stationId={sid}
        stationName={st.name}
        tz={st.tz}
      />
    </main>
  );
}
