"use client";

import { useSyncExternalStore } from "react";

import { formatDay } from "@/lib/billing/format";

const noop = () => () => {};

/** A date as "Dec 3, 2026" in the viewer's own time zone (UTC during server rendering). */
export function LocalDay({ iso }: { iso: string }) {
  const text = useSyncExternalStore(
    noop,
    () => formatDay(iso),
    () => formatDay(iso, "UTC"),
  );
  return <time dateTime={iso}>{text}</time>;
}
