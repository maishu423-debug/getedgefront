"use client";

import { useSyncExternalStore } from "react";

import { useBilling } from "@/lib/billing/client";

import { basePollMs, nextDelay } from "./poll";

/**
 * Premium data in the browser (v2 Phase 10 B1/B7). Only components that already know the viewer
 * is Premium (from the server-computed session) call `usePremiumData`, so free and signed-out
 * visitors never request /api/premium/*. The routes check again on the server.
 *
 * One shared entry per URL: the station cards, chart and board subscribe to the same request
 * (no duplicates across components). Polling runs only while the tab is visible; when it becomes
 * visible again, one request goes out at once. Errors back off (60 s → 2 → 5 min) and the last
 * values stay on screen.
 */
export type PremiumStatus = "loading" | "ok" | "error" | "forbidden";

export interface PremiumState<T> {
  data: T | null;
  status: PremiumStatus;
  /** the last refresh failed (values shown are the previous ones, if any) */
  failed: boolean;
  /** when the browser last received data (ms), for "Updated 21:52Z" */
  updatedAt: number | null;
}

type Entry = {
  state: PremiumState<unknown>;
  subs: Set<() => void>;
  timer: ReturnType<typeof setTimeout> | null;
  failures: number;
  inFlight: boolean;
};

const entries = new Map<string, Entry>();
const INITIAL: PremiumState<unknown> = {
  data: null,
  status: "loading",
  failed: false,
  updatedAt: null,
};
let visibilityHooked = false;

function entry(url: string): Entry {
  let e = entries.get(url);
  if (!e) {
    e = { state: INITIAL, subs: new Set(), timer: null, failures: 0, inFlight: false };
    entries.set(url, e);
  }
  return e;
}

function set(e: Entry, patch: Partial<PremiumState<unknown>>) {
  e.state = { ...e.state, ...patch };
  e.subs.forEach((f) => f());
}

const visible = () => typeof document === "undefined" || document.visibilityState === "visible";

function schedule(url: string, e: Entry) {
  if (e.timer) clearTimeout(e.timer);
  e.timer = null;
  if (!e.subs.size || !visible() || e.state.status === "forbidden") return;
  const base = basePollMs(() => window.localStorage.getItem("ef:poll-ms"));
  e.timer = setTimeout(() => void load(url), nextDelay(e.failures, Math.random(), base));
}

async function load(url: string) {
  const e = entry(url);
  if (e.inFlight) return;
  e.inFlight = true;
  try {
    const res = await fetch(url, { cache: "no-store", credentials: "same-origin" });
    if (res.status === 403) {
      set(e, { status: "forbidden", failed: false }); // no longer Premium: stop asking
      return;
    }
    if (!res.ok) throw new Error(String(res.status));
    const data = (await res.json()) as unknown;
    e.failures = 0;
    set(e, { data, status: "ok", failed: false, updatedAt: Date.now() });
  } catch {
    e.failures += 1;
    set(e, { status: e.state.data ? "ok" : "error", failed: true });
  } finally {
    e.inFlight = false;
    schedule(url, e);
  }
}

function hookVisibility() {
  if (visibilityHooked || typeof document === "undefined") return;
  visibilityHooked = true;
  document.addEventListener("visibilitychange", () => {
    for (const [url, e] of entries) {
      if (!e.subs.size) continue;
      if (visible())
        void load(url); // fetch once at once, then the normal schedule
      else if (e.timer) {
        clearTimeout(e.timer);
        e.timer = null;
      }
    }
  });
}

function subscribe(url: string, cb: () => void): () => void {
  const e = entry(url);
  e.subs.add(cb);
  hookVisibility();
  if (e.subs.size === 1) {
    if (e.state.status === "loading" || !e.state.updatedAt) void load(url);
    else schedule(url, e);
  }
  return () => {
    e.subs.delete(cb);
    if (!e.subs.size && e.timer) {
      clearTimeout(e.timer);
      e.timer = null;
    }
  };
}

const noop = () => () => {};
const OFF: PremiumState<never> = { data: null, status: "loading", failed: false, updatedAt: null };

/** Subscribes to `url` when `enabled`; returns the shared state. */
export function usePremiumData<T>(url: string, enabled: boolean): PremiumState<T> {
  const state = useSyncExternalStore(
    enabled ? (cb) => subscribe(url, cb) : noop,
    () => (enabled ? (entry(url).state as PremiumState<T>) : OFF),
    () => OFF,
  );
  return state;
}

/** The viewer's tier as the server computed it (session). `pending` while the session loads. */
export function usePremiumTier(): { pending: boolean; premium: boolean; signedIn: boolean } {
  const { isPending, billing, signedIn } = useBilling();
  return { pending: isPending, premium: !isPending && billing.tier === "premium", signedIn };
}

/** Test hook (Vitest): forget every entry. */
export function resetPremiumStore(): void {
  for (const e of entries.values()) if (e.timer) clearTimeout(e.timer);
  entries.clear();
}
