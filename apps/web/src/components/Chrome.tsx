import Link from "next/link";

import { HeaderAccount } from "./HeaderAccount";
import { LockIcon } from "./LockIcon";
import { MobileMenu } from "./MobileMenu";

export { LockIcon }; // kept for existing imports

export function Logo() {
  return (
    <Link
      href="/"
      className="flex items-center gap-2.5 text-ink no-underline hover:text-ink"
      aria-label="EdgeFront home"
    >
      <svg width="34" height="22" viewBox="0 0 34 22" aria-hidden>
        <path
          d="M1 17 C9 17 11 7 17 7 S25 17 33 17"
          fill="none"
          stroke="#0A6E69"
          strokeWidth="2.4"
          strokeLinecap="round"
        />
        <path
          d="M7 14.6 L10.6 10.2 L12.4 15.2 Z M15.2 7.4 L19.4 3.6 L19.8 8.6 Z M23.4 11.2 L28 8.8 L26.8 14 Z"
          fill="#0A6E69"
        />
      </svg>
      <span className="font-display text-xl font-bold tracking-[-0.02em]">EdgeFront</span>
    </Link>
  );
}

const navLink =
  "inline-flex min-h-10 items-center rounded-[8px] px-3 text-sm text-muted no-underline hover:text-ink";

export function Header({ active }: { active?: "stations" | "pricing" | "sources" }) {
  const cls = (k: string) => `${navLink} ${active === k ? "font-semibold text-ink" : ""}`;
  return (
    <header className="relative border-b border-border bg-surface">
      {/* Below 640 px: one 64 px row (logo, account, Menu). From 640 px: the full nav. */}
      <div className="mx-auto flex h-16 max-w-(--container-content) items-center gap-x-5 px-4 sm:h-auto sm:min-h-16 sm:flex-wrap sm:gap-y-2 sm:px-8 sm:py-3">
        <Logo />
        <nav aria-label="Main" className="ml-auto hidden flex-wrap items-center gap-1 sm:flex">
          <Link
            href="/"
            className={cls("stations")}
            aria-current={active === "stations" ? "page" : undefined}
          >
            Stations
          </Link>
          <Link href="/pricing" className={`${navLink} gap-1.5`}>
            Map
            <span className="inline-flex items-center gap-1 rounded-full bg-premium-bg px-[7px] py-[3px] text-[10px] font-semibold tracking-[.05em] text-premium-text">
              <LockIcon />
              PRO
            </span>
          </Link>
          <Link
            href="/sources"
            className={cls("sources")}
            aria-current={active === "sources" ? "page" : undefined}
          >
            Sources
          </Link>
          <Link
            href="/pricing"
            className={cls("pricing")}
            aria-current={active === "pricing" ? "page" : undefined}
          >
            Pricing
          </Link>
          <HeaderAccount />
        </nav>
        <div className="ml-auto flex items-center gap-1 sm:hidden">
          <HeaderAccount compact />
          <MobileMenu active={active} />
        </div>
      </div>
    </header>
  );
}

export function Footer({ ecmwf = false, iem = false }: { ecmwf?: boolean; iem?: boolean }) {
  return (
    <footer className="mt-auto bg-footer text-[#C9D1CE]">
      <div className="mx-auto grid max-w-(--container-content) grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-7 px-4 py-9 text-[13px] leading-relaxed sm:px-8">
        <div className="flex flex-col gap-2">
          <span className="font-display text-lg font-bold text-white">EdgeFront</span>
          <span>Observed weather data with its source and time stamp.</span>
          <span className="font-mono text-xs">getedgefront.com</span>
        </div>
        <div className="flex flex-col gap-1.5">
          <span className="font-semibold text-white">Sources</span>
          <span>METAR: NOAA Aviation Weather Center</span>
          <span>Daily summaries, forecasts: National Weather Service</span>
          {iem ? <span>DSM via Iowa Environmental Mesonet, Iowa State University</span> : null}
          {ecmwf ? (
            <span>
              Models: NOAA/NCEP (GFS), NWS (NBM, GFS-MOS, LAMP, PFM); IFS and AIFS contain ECMWF
              open data © ECMWF, CC BY 4.0
            </span>
          ) : null}
          <Link href="/sources" className="text-[#C9D1CE] underline hover:text-white">
            All sources and definitions
          </Link>
        </div>
        <div className="flex flex-col gap-1.5">
          <span className="font-semibold text-white">Independent</span>
          <span>
            EdgeFront is not affiliated with Kalshi, Polymarket or Robinhood. Venue names identify
            which markets use a station.
          </span>
          <span className="text-xs">
            Venue labels are being verified against each market&apos;s rules.
          </span>
        </div>
        <div className="flex flex-col gap-1.5">
          <span className="font-semibold text-white">About</span>
          <Link href="/terms" className="text-[#C9D1CE] underline hover:text-white">
            Terms and data licences
          </Link>
          <Link href="/privacy" className="text-[#C9D1CE] underline hover:text-white">
            Privacy
          </Link>
          <span className="text-xs">Data is provided as received. You decide how to use it.</span>
        </div>
      </div>
    </footer>
  );
}

export function PageShell({
  children,
  active,
  iem,
  ecmwf,
}: {
  children: React.ReactNode;
  active?: "stations" | "pricing" | "sources";
  iem?: boolean;
  /** Pages that show IFS/AIFS values carry the CC BY 4.0 attribution. */
  ecmwf?: boolean;
}) {
  return (
    <>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <Header active={active} />
      {children}
      <Footer iem={iem} ecmwf={ecmwf} />
    </>
  );
}
