"use client";

import { useEffect, useId, useRef, useState } from "react";

import { useNow } from "@/lib/hooks";
import { usePremiumData, usePremiumTier } from "@/lib/premium/client";
import type { HfCurrentResponse, HfExtreme } from "@/lib/premium/types";
import { fmtFExact, type TempValue } from "@/lib/temp";
import { formatLocalTime, formatZulu, minutesSince, relativeAge } from "@/lib/time";
import type { CurrentResponse } from "@/lib/types";

import { Skeleton } from "../states";
import { BigTemp, CardHead, card, CurrentCards } from "./CurrentCards";

/**
 * "Now / high so far / low so far" on the station page (v2 Phase 10 B2). The server renders the
 * free METAR cards for everyone (no Premium value is ever in the HTML); for a Premium viewer the
 * browser then loads the 5-minute values from /api/premium/... and swaps them in.
 */
export const DAY_NOTE =
  "Today = midnight to midnight local standard time (the NWS climate day). Settlement uses each market's named source, which can differ from these values.";

export const INFO_TEXT =
  "Not official METAR reports and no METAR quality control. Whole-°C readings, so each value can be 1–2 °F off the station's own reading. The official daily high and low come from the NWS climate report (CLI).";

export function StationNow({ initial, tz }: { initial: CurrentResponse; tz: string }) {
  const { premium } = usePremiumTier();
  const hf = usePremiumData<HfCurrentResponse>(
    `/api/premium/stations/${initial.station_id}/hf-current`,
    premium,
  );
  let body: React.ReactNode;
  if (!premium || hf.status === "forbidden") {
    body = <CurrentCards initial={initial} tz={tz} />;
  } else if (!hf.data) {
    body =
      hf.status === "error" ? (
        <CurrentCards
          initial={initial}
          tz={tz}
          note={<Note tone="warn">Couldn&apos;t load Premium data · retrying</Note>}
        />
      ) : (
        <PremiumSkeleton />
      );
  } else if (!hf.data.in_feed) {
    body = (
      <CurrentCards
        initial={initial}
        tz={tz}
        note={
          <Note>
            This station isn&apos;t in the 5-minute feed. Values are from the hourly METAR.
          </Note>
        }
      />
    );
  } else {
    body = <PremiumCards data={hf.data} tz={tz} failed={hf.failed} updatedAt={hf.updatedAt} />;
  }
  return (
    <div className="flex flex-col gap-3">
      {body}
      <p className="text-[12.5px] text-muted-2">{DAY_NOTE}</p>
    </div>
  );
}

function Note({ children, tone = "info" }: { children: React.ReactNode; tone?: "info" | "warn" }) {
  return (
    <p
      role="status"
      className={`rounded-[10px] border px-3.5 py-2.5 text-[13px] ${
        tone === "warn"
          ? "border-[#F0DDB8] bg-[#FFF7E8] text-[#6B4600]"
          : "border-[#CFE3E1] bg-[#E6F2F1] text-[#064F4B]"
      }`}
    >
      {children}
    </p>
  );
}

function PremiumSkeleton() {
  return (
    <div className="flex flex-col gap-3" aria-busy="true">
      <Skeleton className="h-[42px] w-full max-w-[620px]" label="Loading 5-minute data" />
      <div className="grid flex-1 grid-cols-[repeat(auto-fit,minmax(240px,1fr))] gap-4">
        {["Current temperature", "Today's high so far", "Today's low so far"].map((t) => (
          <div key={t} className={card}>
            <span className="text-sm font-semibold text-muted">{t}</span>
            <Skeleton className="h-[96px] w-36" label={`Loading ${t.toLowerCase()}`} />
            <Skeleton className="h-[52px] w-full" />
          </div>
        ))}
      </div>
    </div>
  );
}

/** The (i) button: an accessible disclosure, closed with Esc. */
export function InfoButton({ label, children }: { label: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const btn = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        btn.current?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);
  return (
    <span className="relative inline-flex">
      <button
        ref={btn}
        type="button"
        aria-expanded={open}
        aria-controls={id}
        aria-label={label}
        onClick={() => setOpen((o) => !o)}
        className="inline-flex size-7 cursor-pointer items-center justify-center rounded-full border border-current/30 font-serif text-[13px] font-bold italic focus-visible:ring-2 focus-visible:ring-brand/50 focus-visible:outline-none"
      >
        i
      </button>
      <span
        id={id}
        role="note"
        hidden={!open}
        className="absolute top-9 right-0 z-20 w-[min(340px,80vw)] rounded-[10px] border border-border bg-surface p-3.5 text-[13px] leading-normal font-normal text-text-2 shadow-[0_8px_24px_rgba(16,26,28,.16)]"
      >
        {children}
      </span>
    </span>
  );
}

function compareLine(label: string, t: TempValue | null | undefined, at: string | null, tz: string, z = false): string {
  if (!t || !at) return `${label}: none yet today`;
  const when = z ? `at ${formatZulu(at)}` : `at ${formatLocalTime(at, tz)}`;
  return z
    ? `${label} ${when}: ${t.f_rounded}° (${fmtFExact(t)} °F)`
    : `${label}: ${t.f_rounded}° (${fmtFExact(t)} °F) ${when}`;
} // prettier-ignore

function PremiumCards({ data, tz, failed, updatedAt }: {
  data: HfCurrentResponse;
  tz: string;
  failed: boolean;
  updatedAt: number | null;
}) {
  const now = useNow();
  const l = data.latest;
  const stale = data.status !== "ok";
  const age = l && now !== null ? minutesSince(l.observed_at, now) : null;
  const qc = data.so_far.excluded_qc_count;
  const m = data.metar;
  const grey = stale ? "ef-stale" : "";
  const qcLine = qc ? (
    <span className="text-[#6B4600]">
      {qc} reading{qc > 1 ? "s" : ""} excluded (QC)
    </span>
  ) : null;

  return (
    <div className="flex flex-col gap-3" data-testid="premium-now" data-stale={stale || undefined}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-[10px] border border-[#CFE3E1] bg-[#E6F2F1] px-3.5 py-2.5 text-[13.5px] font-medium text-[#064F4B]">
        <span aria-hidden className={`size-[9px] flex-none rounded-full ${stale ? "bg-warn ring-4 ring-warn-halo" : "bg-fresh ring-4 ring-fresh-halo"}`} />
        <span className="min-w-0 flex-1">
          Premium · 5-minute ASOS data via NOAA MADIS
          {l ? (
            <>
              {" "}· latest <span className="font-mono">{formatZulu(l.observed_at)}</span>
              {l.received_at ? <>, received <span className="font-mono">{formatZulu(l.received_at)}</span></> : null}
            </>
          ) : null}
        </span>
        <span className="font-mono text-[12px] text-[#064F4B]/80">
          {failed ? "Connection lost · retrying" : updatedAt ? `Updated ${formatZulu(new Date(updatedAt).toISOString())}` : ""}
        </span>
        <InfoButton label="About 5-minute data">
          {INFO_TEXT}{" "}
          QC: readings that MADIS quality control rejected, questioned or marked bad (X, Q, B) are
          kept but left out of the 5-minute high and low, and counted under the cards.
        </InfoButton>
      </div>
      {stale ? (
        <p role="status" className="text-[13px] font-semibold text-[#6B4600]">
          5-minute data delayed{age !== null ? ` · last reading ${relativeAge(l!.observed_at, now!)}` : ""}
        </p>
      ) : null}
      <div className="grid flex-1 grid-cols-[repeat(auto-fit,minmax(240px,1fr))] gap-4">
        <section aria-labelledby="h-cur" className={card}>
          <CardHead id="h-cur" className="text-muted" tag="5-MIN">Current temperature</CardHead>
          <div className={grey}>
            {l?.temp ? (
              <BigTemp value={l.temp.f_rounded} temp={l.temp} label="Current temperature, 5-minute" />
            ) : (
              <p className="font-display text-[40px] font-semibold text-muted-2">—</p>
            )}
          </div>
          <div className="flex flex-col gap-1 text-[13px] text-text-2">
            {l ? (
              <span>
                Observed <span className="font-mono">{formatZulu(l.observed_at)}</span> ({formatLocalTime(l.observed_at, tz)})
                {now !== null ? ` · ${relativeAge(l.observed_at, now)}` : ""}
              </span>
            ) : (
              <span>No 5-minute reading in the last 2 hours.</span>
            )}
            {l && !l.temp ? <span>The latest reading has no usable temperature.</span> : null}
            <span className="text-muted-2">
              {compareLine("Hourly METAR", m.latest?.temp, m.latest?.observed_at ?? null, tz, true)}
            </span>
          </div>
        </section>
        <Extreme id="h-high" label="Today's high so far" className="text-[#8A3A0E]" num="text-temp" grey={grey}
          e={data.so_far.high} tz={tz} qcLine={qcLine}
          compare={compareLine("Highest hourly METAR", m.high_so_far?.temp, m.high_so_far?.observed_at ?? null, tz)} />
        <Extreme id="h-low" label="Today's low so far" className="text-[#1F5E8C]" num="text-[#1F5E8C]" grey={grey}
          e={data.so_far.low} tz={tz} qcLine={qcLine}
          compare={compareLine("Lowest hourly METAR", m.low_so_far?.temp, m.low_so_far?.observed_at ?? null, tz)} />
      </div>
    </div>
  );
} // prettier-ignore

function Extreme({ id, label, className, num, grey, e, tz, compare, qcLine }: {
  id: string;
  label: string;
  className: string;
  num: string;
  grey: string;
  e: HfExtreme | null;
  tz: string;
  compare: string;
  qcLine: React.ReactNode;
}) {
  return (
    <section aria-labelledby={id} className={card}>
      <CardHead id={id} className={className} tag="5-MIN">{label}</CardHead>
      <div className={grey}>
        {e ? (
          <BigTemp value={e.temp.f_rounded} temp={e.temp} label={`${label}, 5-minute`} className={num} />
        ) : (
          <p className="font-display text-[40px] font-semibold text-muted-2">—</p>
        )}
      </div>
      <div className="flex flex-col gap-1 text-[13px] text-text-2">
        <span>
          {e ? (
            <>At <span className="font-mono">{formatZulu(e.observed_at)}</span> ({formatLocalTime(e.observed_at, tz)})</>
          ) : (
            "No 5-minute reading yet in today's climate day."
          )}
        </span>
        <span className="text-muted-2">{compare}</span>
        {qcLine}
      </div>
    </section>
  );
} // prettier-ignore
