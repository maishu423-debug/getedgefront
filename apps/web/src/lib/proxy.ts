import "server-only";

import { apiInternalUrl } from "./api";

/** Forward one read-only FastAPI endpoint to the browser (FastAPI itself is never exposed). */
export async function proxyGet(path: string): Promise<Response> {
  try {
    const res = await fetch(`${apiInternalUrl()}/api/v1${path}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    const body = await res.text();
    return new Response(body, {
      status: res.status,
      headers: { "content-type": "application/json", "cache-control": "no-store" },
    });
  } catch {
    return Response.json(
      { error: "upstream unavailable" },
      { status: 502, headers: { "cache-control": "no-store" } },
    );
  }
}
