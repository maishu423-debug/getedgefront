import type { Metadata } from "next";

import { PageShell } from "@/components/Chrome";
import { MapPage } from "@/components/map/MapPage";
import { COVERAGE } from "@/lib/coverage";

export const metadata: Metadata = {
  title: "Live station map",
  description: `Premium: every Kalshi, Polymarket and Robinhood settlement station on one map, with ${COVERAGE.sentence.replace("5-minute data", "5-minute ASOS temperatures")} and the high and low so far.`,
  alternates: { canonical: "/map" },
};

/** The same HTML for everyone (no data in it); the browser shows the teaser or the live map. */
export default function Map() {
  return (
    <PageShell active="map">
      <main
        id="main"
        className="mx-auto flex w-full max-w-[1440px] flex-col gap-4 px-4 pt-6 pb-12 sm:px-8"
      >
        <MapPage />
      </main>
    </PageShell>
  );
}
