"use client";

import { usePolling } from "@/lib/hooks";
import { formatZulu } from "@/lib/time";
import type { SourceStatus, StatusResponse } from "@/lib/types";

import { RelativeAge } from "./RelativeAge";

function Item({ label, src }: { label: string; src: SourceStatus | undefined }) {
  if (!src) return null;
  if (!src.healthy) {
    return (
      <span className="text-[#F2B572]">
        {label}:{" "}
        {src.last_success_at ? (
          <>
            last ok {formatZulu(src.last_success_at)}
            <RelativeAge iso={src.last_success_at} prefix=" (" />
            {")"}
          </>
        ) : (
          "no data yet"
        )}
      </span>
    );
  }
  return (
    <span>
      {label} {formatZulu(src.last_success_at)}
    </span>
  );
}

const MODEL_KEYS: [string, string][] = [
  ["model_ifs", "IFS"], ["model_gfs", "GFS"], ["model_aifs", "AIFS"], ["model_gfs_mos", "GFS-MOS"],
  ["model_nbm", "NBM"], ["model_lamp", "LAMP"], ["model_pfm", "PFM"],
]; // prettier-ignore

/** "06Z" for a cycle on the hour, "13:30Z" otherwise. */
function cycleLabel(iso: string | null): string {
  if (!iso) return "—";
  const z = formatZulu(iso);
  return z.endsWith(":00Z") ? z.replace(":00Z", "Z") : z;
}

function Models({ by }: { by: Map<string, SourceStatus> }) {
  const items = MODEL_KEYS.map(([k, label]) => ({ label, s: by.get(k) })).filter((x) => x.s);
  if (!items.length) return null;
  return (
    <span>
      Models in:{" "}
      {items.map(({ label, s }, i) => (
        <span key={label} className={s!.healthy && s!.last_item_time ? "" : "text-[#F2B572]"}>
          {i ? " · " : ""}
          {label} {s!.last_item_time ? cycleLabel(s!.last_item_time) : "none yet"}
        </span>
      ))}
    </span>
  );
}

/** Dark data-status strip (homepage). Refreshes every 60 s while the tab is visible. */
export function StatusStrip({ initial }: { initial: StatusResponse | null }) {
  const { data, failed } = usePolling<StatusResponse | null>("/api/status", initial);
  const by = new Map((data?.sources ?? []).map((s) => [s.key, s]));
  const relevant = ["metar", "cli", "dsm_nws", "dsm_iem", "forecast"].map((k) => by.get(k));
  const allOk = !failed && data !== null && relevant.every((s) => s?.healthy);
  const dsm = [by.get("dsm_nws"), by.get("dsm_iem")].filter((s): s is SourceStatus => !!s);
  const dsmLatest = dsm
    .filter((s) => s.healthy)
    .map((s) => s.last_success_at)
    .sort()
    .at(-1);
  const dsmBad = dsm.find((s) => !s.healthy);

  return (
    <div className="bg-footer text-[#DCE3E0]" aria-label="Data status">
      <div className="mx-auto flex max-w-(--container-content) flex-wrap items-center gap-x-6 gap-y-2 px-4 py-[11px] font-mono text-xs sm:px-8">
        <span className="flex items-center gap-2 font-sans font-semibold text-white">
          <span
            aria-hidden
            className={`size-2 rounded-full ${allOk ? "bg-[#3DD68C]" : "bg-[#F2B572]"}`}
          />
          Data status · {data ? formatZulu(data.generated_at) : "—"}
        </span>
        {data === null ? (
          <span className="text-[#F2B572]">
            Status unavailable: the EdgeFront API is not responding.
          </span>
        ) : (
          <>
            <Item label="METARs fetched" src={by.get("metar")} />
            <span>
              Daily summaries: <Item label="CLI" src={by.get("cli")} />
              {" · "}
              {dsmBad ? (
                <Item label="DSM" src={dsmBad} />
              ) : (
                <span>DSM {formatZulu(dsmLatest)}</span>
              )}
            </span>
            <Item label="NWS forecasts updated" src={by.get("forecast")} />
            <Models by={by} />
            {failed ? (
              <span className="text-[#F2B572]">refresh failed, showing last status</span>
            ) : null}
          </>
        )}
        <span className="text-[#F2B572]">5-min feed: Premium</span>
      </div>
    </div>
  );
}
