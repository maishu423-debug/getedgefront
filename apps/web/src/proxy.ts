import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import registry from "@/generated/stations.json";
import { logJson, rateLimitPerMinute } from "@/lib/deploy";
import { clientIp, hit } from "@/lib/ratelimit";
import { securityHeaders } from "@/lib/security";

/**
 * Runs before every page and route (not static assets):
 * - /api/*: per-IP rate limit → 429 with Retry-After (Phase 6 B5)
 * - station URLs, decided before any rendering starts (owner A4): known id in lower case → 308 to
 *   the canonical upper-case URL; unknown id → the not-found page with a real HTTP 404. With
 *   Cache Components the page always streams its prerendered shell with 200, so this is the only
 *   place a 404 status can come from. The id list is src/generated/stations.json, copied from
 *   data/stations.yaml at build time.
 * - security headers, CSP (report-only until CSP_MODE=enforce), HSTS (once enabled) and
 *   `X-Robots-Tag: noindex` until INDEXING_ENABLED=true.
 */
const KNOWN = new Set(registry.stations.map((s) => s.id));

function withHeaders(res: NextResponse, request: NextRequest): NextResponse {
  const https = request.headers.get("x-forwarded-proto") === "https";
  for (const [k, v] of Object.entries(securityHeaders(https))) res.headers.set(k, v);
  return res;
}

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Stripe's webhook is exempt: every request is signature-checked, and Stripe sends bursts
  // (e.g. many events at once when a subscription renews) from a few shared addresses.
  if (pathname.startsWith("/api/") && pathname !== "/api/stripe/webhook") {
    const ip = clientIp(request.headers);
    const v = hit(ip, Date.now(), rateLimitPerMinute());
    if (!v.ok) {
      logJson("warn", "rate limited", { path: pathname, ip, retry_after_s: v.retryAfterS });
      const res = NextResponse.json(
        { error: "too many requests" },
        {
          status: 429,
          headers: { "Retry-After": String(v.retryAfterS), "Cache-Control": "no-store" },
        },
      );
      return withHeaders(res, request);
    }
    return withHeaders(NextResponse.next(), request);
  }

  const m = /^\/station\/([^/]+)\/?$/.exec(pathname);
  if (m) {
    const raw = decodeURIComponent(m[1]!);
    const upper = raw.toUpperCase();
    if (!KNOWN.has(upper)) {
      const url = request.nextUrl.clone();
      url.pathname = "/_station-not-found"; // no route matches → not-found.tsx, status 404
      return withHeaders(NextResponse.rewrite(url), request);
    }
    if (raw !== upper) {
      const url = request.nextUrl.clone();
      url.pathname = `/station/${upper}`;
      return withHeaders(NextResponse.redirect(url, 308), request);
    }
  }
  return withHeaders(NextResponse.next(), request);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
