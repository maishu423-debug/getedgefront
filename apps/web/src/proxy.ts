import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/** /station/kdfw → 308 /station/KDFW (one canonical, upper-case URL per station). */
export function proxy(request: NextRequest) {
  const m = /^\/station\/([^/]+)\/?$/.exec(request.nextUrl.pathname);
  if (m && m[1] !== m[1]!.toUpperCase()) {
    const url = request.nextUrl.clone();
    url.pathname = `/station/${m[1]!.toUpperCase()}`;
    return NextResponse.redirect(url, 308);
  }
  return NextResponse.next();
}

export const config = { matcher: "/station/:id" };
