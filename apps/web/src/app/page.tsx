import { Suspense } from "react";

import { Board } from "@/components/Board";
import { PageShell } from "@/components/Chrome";
import { MapTeaser, NewHighsFeed } from "@/components/HomeSide";
import { StationSearch } from "@/components/StationSearch";
import { StatusStrip } from "@/components/StatusStrip";
import { Skeleton, UpstreamDown } from "@/components/states";
import { getFeed, getStations, getStatus } from "@/lib/api";

export default function Home() {
  return (
    <PageShell active="stations">
      <section aria-labelledby="h-hero" className="border-b border-border bg-surface">
        <div className="mx-auto flex max-w-(--container-content) flex-col gap-5 px-4 pt-10 pb-8 sm:px-8">
          <div className="flex max-w-[820px] flex-col gap-2.5">
            <h1
              id="h-hero"
              className="font-display text-[32px] leading-[1.08] font-bold tracking-[-0.03em] sm:text-[44px]"
            >
              Observed weather at the U.S. stations weather markets settle on.
            </h1>
            <p className="text-[17px] leading-normal text-[#3A4644]">
              Hourly METARs, NWS daily climate reports and ASOS daily summaries, NWS forecasts and
              model guidance (GFS, ECMWF IFS and AIFS, NBM, GFS-MOS, LAMP and NWS point forecasts)
              for every Kalshi, Polymarket and Robinhood temperature station, each with its source
              and time stamp.
            </p>
          </div>
          <Suspense
            fallback={<Skeleton className="h-[52px] max-w-[760px]" label="Loading search" />}
          >
            <HeroSearch />
          </Suspense>
        </div>
      </section>

      <Suspense fallback={<div className="h-[38px] bg-footer" />}>
        <Strip />
      </Suspense>

      <main
        id="main"
        className="mx-auto flex w-full max-w-(--container-content) flex-wrap items-start gap-6 px-4 pt-7 pb-14 sm:px-8"
      >
        <Suspense
          fallback={
            <div className="flex min-w-0 flex-[999_1_760px] flex-col gap-3">
              <Skeleton className="h-9 w-64" />
              <Skeleton className="h-[640px]" label="Loading station board" />
            </div>
          }
        >
          <BoardSection />
        </Suspense>
        <aside className="flex min-w-0 flex-[1_1_320px] flex-col gap-5">
          <Suspense fallback={<Skeleton className="h-[420px]" label="Loading new highs" />}>
            <Feed />
          </Suspense>
          <MapTeaser />
        </aside>
      </main>
    </PageShell>
  );
}

async function HeroSearch() {
  const res = await getStations();
  const list = res.ok
    ? res.data.stations.map(({ id, name, city, state, aliases }) => ({
        id,
        name,
        city,
        state,
        aliases,
      }))
    : [];
  return <StationSearch stations={list} />;
}

async function Strip() {
  const res = await getStatus();
  return <StatusStrip initial={res.ok ? res.data : null} />;
}

async function BoardSection() {
  const res = await getStations();
  if (!res.ok) {
    return (
      <section className="flex min-w-0 flex-[999_1_760px] flex-col gap-3">
        <h2 className="font-display text-[22px] font-semibold">Settlement stations</h2>
        <UpstreamDown what="The EdgeFront API" />
      </section>
    );
  }
  return (
    <Suspense
      fallback={<Skeleton className="h-[640px] flex-[999_1_760px]" label="Loading station board" />}
    >
      <Board initial={res.data} />
    </Suspense>
  );
}

async function Feed() {
  const res = await getFeed(10);
  return <NewHighsFeed feed={res.ok ? res.data : null} />;
}
