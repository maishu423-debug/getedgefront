import "server-only";

import type { ApiHealth } from "./types";

/** Base URL of the FastAPI service as seen from the Next.js server (private network). */
export function apiInternalUrl(): string {
  return (process.env.API_INTERNAL_URL ?? "http://localhost:8000").replace(/\/+$/, "");
}

export type HealthResult =
  { reachable: true; httpStatus: number; health: ApiHealth } | { reachable: false; error: string };

/** Server-side only. Never cached: health must reflect the live API. */
export async function fetchHealth(): Promise<HealthResult> {
  try {
    const res = await fetch(`${apiInternalUrl()}/api/v1/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(3000),
    });
    const health = (await res.json()) as ApiHealth;
    return { reachable: true, httpStatus: res.status, health };
  } catch (err) {
    return { reachable: false, error: err instanceof Error ? err.name : "unknown error" };
  }
}
