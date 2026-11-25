import "server-only";

import { cacheLife } from "next/cache";
import { connection } from "next/server";

import type {
  ApiHealth,
  CurrentResponse,
  DailySummariesResponse,
  FeedResponse,
  ForecastResponse,
  MetarsResponse,
  ObservedResponse,
  StationResponse,
  StationsResponse,
  StatusResponse,
} from "./types";

/** Base URL of the FastAPI service as seen from the Next.js server (private network). */
export function apiInternalUrl(): string {
  return (process.env.API_INTERNAL_URL ?? "http://localhost:8000").replace(/\/+$/, "");
}

export class ApiNotFound extends Error {}

/** Raw GET (no cache). Throws ApiNotFound on 404 and Error on anything else not OK. */
export async function apiGetUncached<T>(path: string): Promise<T> {
  const res = await fetch(`${apiInternalUrl()}/api/v1${path}`, {
    cache: "no-store",
    signal: AbortSignal.timeout(8000),
  });
  if (res.status === 404) throw new ApiNotFound(path);
  if (!res.ok) throw new Error(`API ${res.status} for ${path}`);
  return (await res.json()) as T;
}

type Cached<T> = { notFound: true } | { notFound: false; data: T };

/**
 * Cached GET shared across requests, revalidated about every 60 s.
 * A 404 is returned as a value: errors thrown across a `use cache` boundary lose their class,
 * so `instanceof ApiNotFound` would never match outside. Other errors are thrown and never cached.
 */
async function apiGetCached<T>(path: string): Promise<Cached<T>> {
  "use cache";
  cacheLife({ stale: 30, revalidate: 60, expire: 240 });
  try {
    return { notFound: false, data: await apiGetUncached<T>(path) };
  } catch (err) {
    if (err instanceof ApiNotFound) return { notFound: true };
    throw err;
  }
}

export type Result<T> = { ok: true; data: T } | { ok: false; notFound: boolean; error: string };

/** Never throws: pages render an "upstream down" state instead of crashing. */
export async function load<T>(path: string): Promise<Result<T>> {
  // Request time only: prerendering stops here, so `next build` never contacts the API.
  // The shared 60 s cache below still applies across requests.
  await connection();
  try {
    const r = await apiGetCached<T>(path);
    if (r.notFound) return { ok: false, notFound: true, error: `not found: ${path}` };
    return { ok: true, data: r.data };
  } catch (err) {
    return {
      ok: false,
      notFound: err instanceof ApiNotFound,
      error: err instanceof Error ? err.message : "unknown error",
    };
  }
}

export const getStations = () => load<StationsResponse>("/stations");
export const getStatus = () => load<StatusResponse>("/status");
export const getFeed = (limit = 10) => load<FeedResponse>(`/feed/new-highs?limit=${limit}`);
export const getStation = (id: string) => load<StationResponse>(`/stations/${id}`);
export const getCurrent = (id: string) => load<CurrentResponse>(`/stations/${id}/current`);
export const getForecast = (id: string) => load<ForecastResponse>(`/stations/${id}/forecast`);
export const getDaily = (id: string) =>
  load<DailySummariesResponse>(`/stations/${id}/daily-summaries`);
export const getObserved = (id: string) =>
  load<ObservedResponse>(`/stations/${id}/observed?hours=24`);
export const getMetars = (id: string) => load<MetarsResponse>(`/stations/${id}/metars?hours=24`);

/** Health is never cached. */
export async function fetchHealth(): Promise<Result<ApiHealth>> {
  try {
    return { ok: true, data: await apiGetUncached<ApiHealth>("/health") };
  } catch (err) {
    return { ok: false, notFound: false, error: err instanceof Error ? err.name : "unknown" };
  }
}
