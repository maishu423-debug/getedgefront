import type { Metadata } from "next";
import Link from "next/link";

import { LockIcon, PageShell } from "@/components/Chrome";

export const metadata: Metadata = {
  title: "Pricing",
  description:
    "EdgeFront Free and Premium. Free is available now; Premium (5-minute data, live map) is coming later.",
  alternates: { canonical: "/pricing" },
};

const ROWS: [string, string, string][] = [
  ["Hourly METAR + SPECI (raw and decoded)", "yes", "yes"],
  ["NWS Daily Climate Report (CLI) and ASOS Daily Summary (DSM)", "yes", "yes"],
  ["NWS forecast (today and hourly)", "yes", "yes"],
  [
    "Model guidance chart (GFS, IFS, AIFS, NBM, GFS-MOS, LAMP, PFM)",
    "Coming in a later update",
    "Coming in a later update",
  ],
  [
    "Current temperature, high so far and observed chart",
    "From hourly METARs",
    "From 5-minute ASOS data",
  ],
  ["Continuous 5-minute ASOS data", "—", "yes"],
  ["Live station map", "—", "yes"],
  ["More data sources", "—", "Later"],
];

const FAQ: [string, string][] = [
  [
    "What does “5-minute data” mean?",
    "Automated airport weather stations (ASOS) measure every few minutes, but the hourly METAR only reports one value per hour (plus special reports). Premium will show the high-frequency 5-minute observations NOAA distributes, so you can see what happens between hourly reports.",
  ],
  [
    "Where does the data come from?",
    "METARs from the NOAA Aviation Weather Center; Daily Climate Reports, ASOS Daily Summaries and forecasts from the National Weather Service (some ASOS Daily Summaries via the Iowa Environmental Mesonet). Every value shows its source and time stamp. See Sources for details.",
  ],
  [
    "Does EdgeFront give trading advice?",
    "No. EdgeFront shows weather data as received. It does not forecast, rank models, show market prices or tell you what to trade.",
  ],
  [
    "Which value settles a market?",
    "The venue's own rules decide outcomes, and venues name different sources (for example an NWS climate report or another provider). Always read the market's rules. EdgeFront's “high so far” is not a settlement value.",
  ],
];

function Cell({ v }: { v: string }) {
  if (v === "yes")
    return (
      <span className="font-semibold text-fresh">
        <span aria-hidden>✓</span>
        <span className="sr-only">Included</span>
      </span>
    );
  if (v === "—") return <span className="text-muted-2">Not included</span>;
  return <span className="text-text-2">{v}</span>;
}

export default function PricingPage() {
  return (
    <PageShell active="pricing">
      <main
        id="main"
        className="mx-auto flex w-full max-w-[960px] flex-col gap-8 px-4 pt-10 pb-16 sm:px-8"
      >
        <div className="flex flex-col gap-2">
          <h1 className="font-display text-[36px] font-bold tracking-[-0.02em]">Pricing</h1>
          <p className="max-w-2xl text-text-2">
            EdgeFront Free is available now, with no account needed. Premium adds high-frequency
            data and a live map; it is not available yet.
          </p>
        </div>

        <div className="grid grid-cols-[repeat(auto-fit,minmax(260px,1fr))] gap-4">
          <div className="flex flex-col gap-3 rounded-[16px] border border-border bg-surface p-6">
            <h2 className="font-display text-xl font-semibold">Free</h2>
            <p className="text-sm text-text-2">Everything on the site today. No sign-up.</p>
            <Link
              href="/"
              className="inline-flex min-h-10 items-center self-start rounded-[9px] bg-brand px-4 text-sm font-semibold text-white no-underline hover:bg-brand-hover hover:text-white"
            >
              Open the station board
            </Link>
          </div>
          <div className="flex flex-col gap-3 rounded-[16px] border border-[#F0DDB8] bg-[#FFFBF4] p-6">
            <h2 className="flex items-center gap-2 font-display text-xl font-semibold">
              Premium
              <span className="inline-flex items-center gap-1 rounded-full bg-premium-bg px-2 py-[3px] text-[10px] font-semibold tracking-[.06em] text-premium-text">
                <LockIcon />
                COMING SOON
              </span>
            </h2>
            <p className="text-sm text-text-2">
              5-minute ASOS data, a live station map and more sources.
            </p>
            <button
              type="button"
              disabled
              aria-disabled
              className="inline-flex min-h-10 cursor-not-allowed items-center self-start rounded-[9px] bg-[#E7EAE6] px-4 text-sm font-semibold text-muted"
            >
              Coming soon
            </button>
          </div>
        </div>

        <div className="overflow-hidden rounded-[14px] border border-border bg-surface">
          <div className="relative overflow-x-auto">
            <table className="w-full border-collapse text-sm [&_td]:border-b [&_td]:border-hairline [&_td]:px-4 [&_td]:py-3 [&_th]:border-b [&_th]:border-border [&_th]:bg-[#FAFBF9] [&_th]:px-4 [&_th]:py-3 [&_th]:text-left [&_th]:text-xs [&_th]:font-semibold [&_th]:tracking-[.04em] [&_th]:text-muted-2 [&_th]:uppercase">
              <caption className="sr-only">Free and Premium features</caption>
              <thead>
                <tr>
                  <th scope="col">Feature</th>
                  <th scope="col">Free</th>
                  <th scope="col">Premium</th>
                </tr>
              </thead>
              <tbody>
                {ROWS.map(([f, a, b]) => (
                  <tr key={f}>
                    <th
                      scope="row"
                      className="!border-hairline !bg-transparent !text-sm !font-normal !tracking-normal !text-ink !normal-case"
                    >
                      {f}
                    </th>
                    <td>
                      <Cell v={a} />
                    </td>
                    <td>
                      <Cell v={b} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <section aria-labelledby="h-faq" className="flex flex-col gap-4">
          <h2 id="h-faq" className="font-display text-2xl font-semibold">
            Questions
          </h2>
          {FAQ.map(([q, a]) => (
            <div key={q} className="rounded-[12px] border border-border bg-surface p-5">
              <h3 className="font-semibold">{q}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-text-2">{a}</p>
            </div>
          ))}
        </section>
      </main>
    </PageShell>
  );
}
