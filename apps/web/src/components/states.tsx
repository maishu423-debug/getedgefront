/** Shared state components (owner B2). Every block uses these; never an empty box or NaN. */

import Link from "next/link";
import type { ReactNode } from "react";

import { RelativeAge } from "./RelativeAge";

export function Skeleton({
  className = "",
  label = "Loading",
}: {
  className?: string;
  label?: string;
}) {
  return (
    <div
      role="status"
      aria-label={label}
      className={`animate-pulse rounded-[10px] bg-[#E7EAE6] ${className}`}
    />
  );
}

function Box({
  tone,
  title,
  children,
}: {
  tone: "neutral" | "warn";
  title: string;
  children?: ReactNode;
}) {
  const cls =
    tone === "warn"
      ? "border-warn/40 bg-warn-halo text-[#6B4600]"
      : "border-border bg-[#FAFBF9] text-text-2";
  return (
    <div role="status" className={`rounded-[10px] border px-4 py-3 text-sm ${cls}`}>
      <p className="font-semibold">{title}</p>
      {children ? <div className="mt-1 text-[13px] leading-relaxed">{children}</div> : null}
    </div>
  );
}

export function NoData({ what = "data", children }: { what?: string; children?: ReactNode }) {
  return (
    <Box tone="neutral" title={`No ${what} received yet`}>
      {children ??
        "EdgeFront checks the source on a schedule; this fills in when the first report arrives."}
    </Box>
  );
}

export function NotAvailable({ children }: { children?: ReactNode }) {
  return (
    <Box
      tone="neutral"
      title={typeof children === "string" ? children : "Not published for this station"}
    />
  );
}

export function UpstreamDown({
  lastOk,
  what = "The data source",
}: {
  lastOk?: string | null;
  what?: string;
}) {
  return (
    <Box tone="warn" title={`${what} is not responding right now`}>
      {lastOk ? (
        <>
          Showing the last data received
          <RelativeAge iso={lastOk} prefix=" · last ok " />.
        </>
      ) : (
        "No data has been received yet."
      )}
    </Box>
  );
}

/** Amber pill: "Stale · last report 2 h ago". */
export function StaleBadge({ since }: { since: string | null | undefined }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-warn-halo px-2 py-0.5 text-[11.5px] font-semibold text-[#6B4600]">
      <span aria-hidden className="size-1.5 rounded-full bg-warn" />
      Stale
      {since ? <RelativeAge iso={since} prefix=" · last report " /> : null}
    </span>
  );
}

export function FreshDot({ stale }: { stale: boolean }) {
  return (
    <span
      aria-hidden
      className={`inline-block size-[9px] flex-none rounded-full ${
        stale ? "bg-warn ring-4 ring-warn-halo" : "bg-fresh ring-4 ring-fresh-halo"
      }`}
    />
  );
}

export function StationNotFound({ id }: { id?: string }) {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-lg font-semibold">
        {id ? (
          <>
            We don&apos;t track a station called <span className="font-mono">{id}</span>.
          </>
        ) : (
          "Station not found."
        )}
      </p>
      <p className="text-text-2">
        EdgeFront covers the U.S. stations that weather markets settle on.{" "}
        <Link href="/">See all stations</Link>.
      </p>
    </div>
  );
}
