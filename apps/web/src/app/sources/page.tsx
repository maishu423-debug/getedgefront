import type { Metadata } from "next";
import { Suspense } from "react";

import { PageShell } from "@/components/Chrome";
import { RelativeAge } from "@/components/RelativeAge";
import { Skeleton } from "@/components/states";
import { getStatus } from "@/lib/api";
import { formatZulu } from "@/lib/time";
import type { SourceStatus } from "@/lib/types";

export const metadata: Metadata = {
  title: "Sources and definitions",
  description:
    "Where EdgeFront's data comes from, how often it is checked, licences and attribution, and how observed time, age, the climate day and “high so far” are defined.",
  alternates: { canonical: "/sources" },
};

interface SourceCard {
  title: string;
  producer: string;
  uses: string;
  cadence: string;
  licence: string;
  keys: string[];
  url: string;
  /** shown instead of the live source status (sources not on the public status strip) */
  statusNote?: string;
}

const SOURCES: SourceCard[] = [
  {
    title: "NOAA Aviation Weather Center",
    producer: "NOAA / National Weather Service",
    uses: "Hourly METAR and SPECI reports for every station: raw text, plus EdgeFront's decoding (temperature, dew point, wind, visibility, sky, pressure, 6- and 24-hour max/min groups).",
    cadence: "Checked every 3 minutes (aviationweather.gov Data API).",
    licence: "U.S. government data, public domain.",
    keys: ["metar"],
    url: "https://aviationweather.gov/data/api/",
  },
  {
    title: "National Weather Service (api.weather.gov)",
    producer: "National Weather Service",
    uses: "Daily Climate Reports (CLI) for 26 stations; ASOS Daily Summaries (DSM) for KNYC, KMSP and KSAT; the 7-day and hourly forecast for each station's NWS grid point.",
    cadence:
      "CLI every 15 minutes, DSM every 12 minutes, forecasts every 30 minutes (respecting the API's cache headers).",
    licence: "U.S. government data, public domain.",
    keys: ["cli", "dsm_nws", "forecast"],
    url: "https://www.weather.gov/documentation/services-web-api",
  },
  {
    title: "Iowa Environmental Mesonet (IEM)",
    producer: "Iowa State University, mirroring the NWS text product stream",
    uses: "ASOS Daily Summaries (DSM) for the other 24 stations. The NWS issues these products; IEM's archive carries them where api.weather.gov does not.",
    cadence:
      "One small request per station every 12 minutes; product text only when a new product appears.",
    licence:
      "Described by IEM as public domain, usable for any lawful purpose, no warranty. Attribution: DSM via Iowa Environmental Mesonet, Iowa State University.",
    keys: ["dsm_iem"],
    url: "https://mesonet.agron.iastate.edu/",
  },
];

/** Premium (v2 Phases 9–10): the 5-minute data and the live map's basemap. */
const PREMIUM_SOURCES: SourceCard[] = [
  {
    title: "5-minute ASOS data (NOAA MADIS) · Premium",
    producer: "FAA ASOS stations, via the NOAA Meteorological Assimilation Data Ingest System",
    uses: "5-minute temperature, dew point, wind, pressure and visibility for the 26 settlement stations in the feed (KNYC and KBKF are not in it; Premium shows their hourly METAR). Temperatures are whole °C, so each value can be 1–2 °F off the station's own reading: we show the possible readings next to the rounded and unrounded °F. These are not official METAR reports and have no METAR quality control; MADIS quality-control flags are kept, and readings MADIS rejected or questioned are left out of the 5-minute high and low.",
    cadence:
      "Checked every minute. A reading usually reaches us 10–20 minutes after it was observed (MADIS file production); a station counts as delayed after 30 minutes.",
    licence:
      "Public data (MADIS distribution category 3, no restrictions). Attribution: 5-minute ASOS observations from the NOAA Meteorological Assimilation Data Ingest System (MADIS), provided by the FAA. Data as received; not official METAR observations.",
    keys: [],
    statusNote:
      "Shown on the status page as its own block (latest file, reading delay, stations reporting).",
    url: "https://madis.ncep.noaa.gov/madis_OMO.shtml",
  },
  {
    title: "Live map basemap · Premium",
    producer: "OpenFreeMap, OpenMapTiles and OpenStreetMap contributors; U.S. Census Bureau",
    uses: "The street map under the station markers on /map (OpenFreeMap's public instance, Positron style). If it can't be reached, the map switches to a simple outline of the contiguous U.S. drawn from the Census Bureau's cartographic boundary files, served by EdgeFront itself.",
    cadence: "Map tiles load in your browser while you use the map (Premium members only).",
    licence:
      "Map data © OpenStreetMap contributors, available under the Open Database License (ODbL). Tile schema and design © OpenMapTiles (CC BY 4.0). Served by OpenFreeMap (no warranty or uptime guarantee). The credits are always shown on the map. Outline: U.S. Census Bureau cartographic boundaries (2017), public domain.",
    keys: [],
    statusNote:
      "Not monitored: if the street map fails, the map falls back to the outline automatically.",
    url: "https://openfreemap.org/",
  },
];

/** Model guidance (Phase 5). Shown as MODEL DATA on station pages; never blended or ranked. */
const MODEL_SOURCES: SourceCard[] = [
  {
    title: "GFS (Global Forecast System)",
    producer: "NOAA / NCEP",
    uses: "2 m temperature, dew point and relative humidity, 10 m wind, total cloud cover at the nearest land grid point (0.25°), hourly to 54 h. Only these fields are downloaded (byte ranges).",
    cadence:
      "Checked every 15 minutes for the 00/06/12/18Z runs; each step is stored as soon as it is published. Files from the NOAA Open Data bucket on AWS, NOMADS as a fallback.",
    licence: "U.S. government data, public domain.",
    keys: ["model_gfs"],
    url: "https://registry.opendata.aws/noaa-gfs-bdp-pds/",
  },
  {
    title: "ECMWF IFS and AIFS (open data)",
    producer: "European Centre for Medium-Range Weather Forecasts",
    uses: "IFS (the ECMWF physics model, 3-hourly) and AIFS Single (ECMWF's machine-learning model, 6-hourly): 2 m temperature and dew point, 10 m wind and total cloud cover at the nearest land grid point (0.25°) to 54 h. Relative humidity is computed from temperature and dew point.",
    cadence: "Checked every 15 minutes for the 00/06/12/18Z runs.",
    licence:
      "ECMWF open data, licensed under Creative Commons Attribution 4.0 (CC BY 4.0). Attribution: contains ECMWF open data © ECMWF. EdgeFront extracts the values at each station's grid point and converts units (K → °F, m/s → kt, fraction → %).",
    keys: ["model_ifs", "model_aifs"],
    url: "https://www.ecmwf.int/en/forecasts/datasets/open-data",
  },
  {
    title: "NWS station guidance: NBM, GFS-MOS, LAMP",
    producer:
      "National Weather Service (National Blend of Models; Meteorological Development Laboratory)",
    uses: "The station text bulletins on NOMADS: NBM hourly (NBH, first ~25 h) then 3-hourly (NBS); GFS MOS (MAV, 3-hourly, cloud as categories); GFS LAMP (LAV, hourly for 25 h, cloud as categories). Temperature, dew point, wind and cloud as printed; relative humidity computed.",
    cadence: "Checked every 15 minutes: NBM and LAMP update hourly, GFS-MOS four times a day.",
    licence: "U.S. government data, public domain.",
    keys: ["model_nbm", "model_gfs_mos", "model_lamp"],
    url: "https://nomads.ncep.noaa.gov/",
  },
  {
    title: "NWS Point Forecast Matrices (PFM)",
    producer: "National Weather Service forecast offices (api.weather.gov)",
    uses: "The 3-hourly temperature, dew point, relative humidity, wind (mph, shown in kt) and cloud category for the forecast point at the station (26 of 28 stations; KMIA and KHOU have no point within 3 km).",
    cadence: "Checked every 15 minutes; offices issue new matrices a few times a day.",
    licence: "U.S. government data, public domain.",
    keys: ["model_pfm"],
    url: "https://www.weather.gov/documentation/services-web-api",
  },
];

function Health({ s }: { s: SourceStatus | undefined }) {
  if (!s) return <span className="text-muted-2">No status</span>;
  return (
    <span
      className={`inline-flex items-center gap-1.5 ${s.healthy ? "text-fresh" : "text-[#8A4100]"}`}
    >
      <span aria-hidden className={`size-2 rounded-full ${s.healthy ? "bg-fresh" : "bg-warn"}`} />
      <span className="font-semibold">{s.healthy ? "OK" : "Delayed"}</span>
      <span className="text-text-2">
        {s.label}: last ok {formatZulu(s.last_success_at)}
        <RelativeAge iso={s.last_success_at} prefix=" · " />
      </span>
    </span>
  );
}

async function LiveHealth({ keys }: { keys: string[] }) {
  const res = await getStatus();
  if (!res.ok) return <span className="text-[#8A4100]">Live status unavailable right now.</span>;
  const by = new Map(res.data.sources.map((s) => [s.key, s]));
  return (
    <ul className="flex flex-col gap-1 text-[13px]">
      {keys.map((k) => (
        <li key={k}>
          <Health s={by.get(k)} />
        </li>
      ))}
    </ul>
  );
}

const DEFS: [string, string][] = [
  [
    "Observed time",
    "When the sensor measured the value (the report's own time). Shown in UTC (Z) and the station's local time.",
  ],
  [
    "Received / fetched time",
    "When the data reached EdgeFront. Upstream products can arrive minutes after they are observed or issued.",
  ],
  [
    "Age and “stale”",
    "Age is now minus observed time. A station's METAR is marked stale (amber) when the latest report is more than 90 minutes old. A source is marked delayed when its last successful check is older than three times its schedule.",
  ],
  [
    "Climate day",
    "Midnight to midnight local standard time, the day the NWS uses for its climate reports. During daylight saving time it runs from 1:00 AM to 1:00 AM on the local clock.",
  ],
  [
    "High and low so far",
    "The highest (lowest) temperature in any hourly METAR or SPECI since the start of the climate day, plus 6-hour maximum (minimum) groups whose whole 6-hour window falls inside the day. They are not settlement values.",
  ],
  [
    "Rounded and unrounded °F",
    "The big number is whole °F, rounded the NWS way (a fraction of .5 or more rounds up, so 36.5 → 37 and −8.5 → −8). The small number is the exact conversion of the reported °C. Most airport stations (ASOS) measure in whole °F, and the METAR's tenths of a °C are a conversion of that reading, so the rounded °F is usually the station's own reading. When only whole °C is available (some reports, and the 5-minute data), it can be 1–2 °F off the station's reading, so we show the possible readings. The official daily high and low are in the NWS Daily Climate Report (CLI).",
  ],
  [
    "METAR vs DSM vs CLI",
    "METARs are point readings, usually once an hour. The ASOS Daily Summary (DSM) and the NWS Daily Climate Report (CLI) report the day's true maximum and minimum from the sensor, including peaks between hourly reports, so they can be higher (or lower) than the METAR high. Intraday CLI and DSM issues cover the day so far; the final issue arrives after local midnight. Markets name their own settlement source: read each market's rules.",
  ],
  [
    "Model guidance",
    "Third-party model output, labelled MODEL DATA. Each model shows its latest run: values only at the model's own valid times (never interpolated), at the nearest land grid point (land fraction at least 0.5) or the NWS forecast point, with no height or bias adjustment. “Received” is when EdgeFront first got the run; a run received more than twice the model's usual interval ago is marked stale. Cloud categories (CL, FW, SC, BK, OV; PFM B1/B2) are plotted at fixed midpoints and shown as categories. “Today” is the climate day; “48 h” starts at the climate day's start. EdgeFront does not rank, blend or endorse models.",
  ],
  [
    "Units",
    "Temperatures in °F, rounded to whole degrees with the NWS rule (.5 rounds up) from the reported °C, with the unrounded value alongside. METAR wind in knots; DSM and CLI wind in mph, as published. Model wind in knots (PFM is published in mph and converted).",
  ],
];

export default function SourcesPage() {
  return (
    <PageShell active="sources" iem ecmwf>
      <main
        id="main"
        className="mx-auto flex w-full max-w-[960px] flex-col gap-8 px-4 pt-10 pb-16 sm:px-8"
      >
        <div className="flex flex-col gap-2">
          <h1 className="font-display text-[36px] font-bold tracking-[-0.02em]">
            Sources and definitions
          </h1>
          <p className="max-w-2xl text-text-2">
            EdgeFront shows data as received from these sources, each value with its source and time
            stamp. It does not change, fill in or forecast values.
          </p>
        </div>
        <section aria-labelledby="h-src" className="flex flex-col gap-4">
          <h2 id="h-src" className="sr-only">
            Data sources
          </h2>
          {[...SOURCES, ...PREMIUM_SOURCES, ...MODEL_SOURCES].map((s) => (
            <article
              key={s.title}
              className="flex flex-col gap-3 rounded-[14px] border border-border bg-surface p-5"
            >
              <div className="flex flex-col gap-0.5">
                <h3 className="font-display text-lg font-semibold">{s.title}</h3>
                <span className="text-[13px] text-muted-2">{s.producer}</span>
              </div>
              <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-[140px_1fr]">
                <dt className="font-semibold text-muted">What we use</dt>
                <dd className="text-text-2">{s.uses}</dd>
                <dt className="font-semibold text-muted">How often</dt>
                <dd className="text-text-2">{s.cadence}</dd>
                <dt className="font-semibold text-muted">Licence</dt>
                <dd className="text-text-2">{s.licence}</dd>
                <dt className="font-semibold text-muted">Live status</dt>
                <dd>
                  {s.statusNote ? (
                    <span className="text-[13px] text-text-2">{s.statusNote}</span>
                  ) : (
                    <Suspense fallback={<Skeleton className="h-5 w-64" label="Loading status" />}>
                      <LiveHealth keys={s.keys} />
                    </Suspense>
                  )}
                </dd>
              </dl>
              <a href={s.url} className="self-start text-sm">
                {s.url.replace(/^https:\/\//, "").replace(/\/$/, "")}
              </a>
            </article>
          ))}
        </section>
        <section aria-labelledby="h-defs" className="flex flex-col gap-3">
          <h2 id="h-defs" className="font-display text-2xl font-semibold">
            Definitions
          </h2>
          <dl className="flex flex-col divide-y divide-hairline rounded-[14px] border border-border bg-surface">
            {DEFS.map(([t, d]) => (
              <div key={t} className="flex flex-col gap-1 px-5 py-4">
                <dt className="font-semibold">{t}</dt>
                <dd className="text-sm leading-relaxed text-text-2">{d}</dd>
              </div>
            ))}
          </dl>
        </section>
      </main>
    </PageShell>
  );
}
