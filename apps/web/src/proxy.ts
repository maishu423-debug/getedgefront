import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import registry from "@/generated/stations.json";

/**
 * Station URLs, decided before any rendering starts (owner A4, 2026-11-25):
 * - known id in lower case → 308 to the canonical upper-case URL
 * - unknown id → the not-found page with a real HTTP 404
 * With Cache Components the page always streams its prerendered shell with 200, so this is
 * the only place a 404 status can come from. The id list is not kept here by hand: it is
 * src/generated/stations.json, copied from data/stations.yaml at build time.
 */
const KNOWN = new Set(registry.stations.map((s) => s.id));

export function proxy(request: NextRequest) {
  const m = /^\/station\/([^/]+)\/?$/.exec(request.nextUrl.pathname);
  if (!m) return NextResponse.next();
  const raw = decodeURIComponent(m[1]!);
  const upper = raw.toUpperCase();
  if (!KNOWN.has(upper)) {
    const url = request.nextUrl.clone();
    url.pathname = "/_station-not-found"; // no route matches → not-found.tsx, status 404
    return NextResponse.rewrite(url);
  }
  if (raw !== upper) {
    const url = request.nextUrl.clone();
    url.pathname = `/station/${upper}`;
    return NextResponse.redirect(url, 308);
  }
  return NextResponse.next();
}

export const config = { matcher: "/station/:id" };
