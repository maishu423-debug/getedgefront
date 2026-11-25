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
    "High so far",
    "The highest temperature in any hourly METAR or SPECI since the start of the climate day, plus 6-hour maximum groups whose whole 6-hour window falls inside the day. It is not a settlement value.",
  ],
  [
    "METAR vs DSM vs CLI",
    "METARs are point readings, usually once an hour. The ASOS Daily Summary (DSM) and the NWS Daily Climate Report (CLI) report the day's true maximum and minimum from the sensor, including peaks between hourly reports, so they can be higher (or lower) than the METAR high. Intraday CLI and DSM issues cover the day so far; the final issue arrives after local midnight. Markets name their own settlement source: read each market's rules.",
  ],
  [
    "Units",
    "Temperatures in °F, rounded to whole degrees (half away from zero) from the reported °C. METAR wind in knots; DSM and CLI wind in mph, as published.",
  ],
];

export default function SourcesPage() {
  return (
    <PageShell active="sources" iem>
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
          {SOURCES.map((s) => (
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
                  <Suspense fallback={<Skeleton className="h-5 w-64" label="Loading status" />}>
                    <LiveHealth keys={s.keys} />
                  </Suspense>
                </dd>
              </dl>
              <a href={s.url} className="self-start text-sm">
                {s.url.replace(/^https:\/\//, "").replace(/\/$/, "")}
              </a>
            </article>
          ))}
          <p className="text-[13px] text-muted-2">
            Model guidance sources are added here when model data launches.
          </p>
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
