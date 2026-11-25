import { connection } from "next/server";

import { apiInternalUrl } from "@/lib/api";
import { logJson } from "@/lib/deploy";
import type { StatusResponse } from "@/lib/types";

/**
 * Public health for uptime monitors (Phase 6 B7). 200 + `"status":"ok"` when the web server, the
 * API and its database answer and every ingest source is healthy; 200 + `"status":"degraded"`
 * (with the unhealthy source keys) when a source is late; 503 when the API or its database is
 * down. Error details stay in the logs.
 */
export async function GET() {
  await connection();
  const base = apiInternalUrl();
  const headers = { "cache-control": "no-store" };
  try {
    const [h, st] = await Promise.all([
      fetch(`${base}/api/v1/health`, { cache: "no-store", signal: AbortSignal.timeout(5000) }),
      fetch(`${base}/api/v1/status`, { cache: "no-store", signal: AbortSignal.timeout(5000) }),
    ]);
    const health = (await h.json()) as { status: string; db: string };
    if (!h.ok || health.db !== "ok") {
      logJson("error", "health: api or db down", { api_status: h.status, db: health.db });
      return Response.json(
        { status: "down", api: h.ok ? "ok" : "error", db: health.db },
        { status: 503, headers },
      );
    }
    const status = (await st.json()) as StatusResponse;
    const unhealthy = status.sources.filter((s) => !s.healthy).map((s) => s.key);
    return Response.json(
      {
        status: unhealthy.length ? "degraded" : "ok",
        api: "ok",
        db: "ok",
        unhealthy_sources: unhealthy,
        checked_at: new Date().toISOString(),
      },
      { headers },
    );
  } catch (err) {
    logJson("error", "health: api unreachable", { error: err instanceof Error ? err.name : "?" });
    return Response.json({ status: "down", api: "unreachable" }, { status: 503, headers });
  }
}
