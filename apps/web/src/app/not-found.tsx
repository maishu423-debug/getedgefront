import { Suspense } from "react";
import Link from "next/link";

import { PageShell } from "@/components/Chrome";
import { StationSearch } from "@/components/StationSearch";
import { Skeleton } from "@/components/states";
import { getStations } from "@/lib/api";

export default function NotFound() {
  return (
    <PageShell>
      <main
        id="main"
        className="mx-auto flex w-full max-w-[760px] flex-col gap-5 px-4 pt-14 pb-20 sm:px-8"
      >
        <p className="font-mono text-sm text-muted-2">404</p>
        <h1 className="font-display text-[36px] font-bold tracking-[-0.02em]">
          We couldn&apos;t find that page
        </h1>
        <p className="text-text-2">
          If you were looking for a station, search for it by city, code (e.g. KDFW) or nickname
          (e.g. NYC).
        </p>
        <Suspense fallback={<Skeleton className="h-[52px]" label="Loading search" />}>
          <Search />
        </Suspense>
        <p>
          <Link href="/">See all stations</Link>
        </p>
      </main>
    </PageShell>
  );
}

async function Search() {
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
