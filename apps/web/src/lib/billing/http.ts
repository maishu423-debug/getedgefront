import "server-only";

import { NextResponse } from "next/server";

import { trustedOrigins } from "@/lib/auth/server";

/** JSON response that is never cached. */
export function json(body: unknown, status = 200): NextResponse {
  return NextResponse.json(body, { status, headers: { "Cache-Control": "no-store" } });
}

/**
 * Billing actions are POSTs from our own pages: refuse other origins (CSRF), and requests whose
 * Origin is missing (browsers always send it on a POST fetch).
 */
export function fromOurSite(req: Request): boolean {
  const origin = req.headers.get("origin");
  return origin !== null && trustedOrigins().includes(origin);
}
