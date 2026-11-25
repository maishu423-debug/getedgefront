"use client";

import { useEffect, useState } from "react";

/** Current time, but only after mount (null during SSR + hydration), ticking every `ms`. */
export function useNow(ms = 30_000): number | null {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    const first = setTimeout(() => setNow(Date.now()), 0);
    const id = setInterval(() => setNow(Date.now()), ms);
    return () => {
      clearTimeout(first);
      clearInterval(id);
    };
  }, [ms]);
  return now;
}

/**
 * Re-fetch `url` (a same-origin /api/* proxy) every `ms` while the tab is visible.
 * Keeps showing the last good data if a refresh fails, and reports the failure.
 */
export function usePolling<T>(url: string, initial: T, ms = 60_000): { data: T; failed: boolean } {
  const [data, setData] = useState<T>(initial);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | null = null;
    let cancelled = false;

    const tick = async () => {
      try {
        const res = await fetch(url, { cache: "no-store" });
        if (!res.ok) throw new Error(String(res.status));
        const json = (await res.json()) as T;
        if (!cancelled) {
          setData(json);
          setFailed(false);
        }
      } catch {
        if (!cancelled) setFailed(true);
      }
    };
    const start = () => {
      if (timer === null) timer = setInterval(tick, ms);
    };
    const stop = () => {
      if (timer !== null) clearInterval(timer);
      timer = null;
    };
    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        void tick();
        start();
      } else {
        stop();
      }
    };
    if (document.visibilityState === "visible") start();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      cancelled = true;
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [url, ms]);

  return { data, failed };
}

/**
 * True once the element is within `margin` of the viewport (then stays true). Charts use it so
 * ECharts is only downloaded and run when the reader gets near them (Phase 6 B1: the charts are
 * below the fold and must not compete with the first paint).
 */
export function useNearViewport<T extends Element>(
  ref: React.RefObject<T | null>,
  margin = "300px",
): boolean {
  const [near, setNear] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || near) return;
    if (typeof IntersectionObserver === "undefined") {
      const t = setTimeout(() => setNear(true), 0);
      return () => clearTimeout(t);
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setNear(true);
          io.disconnect();
        }
      },
      { rootMargin: margin },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [ref, margin, near]);
  return near;
}
