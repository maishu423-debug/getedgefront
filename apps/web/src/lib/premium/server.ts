import "server-only";

import { createHash } from "node:crypto";

import { apiInternalUrl } from "@/lib/api";
import { getAuth } from "@/lib/auth/server";
import { getViewer } from "@/lib/auth/viewer";
import { logJson } from "@/lib/deploy";

import { limitStep, type LimitRow } from "./limit";

/**
 * Premium data routes (v2 Phase 10 B1, CONTEXT V2.4). Each request:
 * 1. checks the session and the entitlement (computed on the server from billing.subscriptions,
 *    never from anything the browser sends);
 * 2. applies the per-user limit;
 * 3. calls the internal FastAPI with X-Internal-Token;
 * 4. answers `private, no-store`. Free and signed-out users get a 403 with no data.
 * Log lines carry the route and a short non-reversible user reference, never an email or id.
 */
const NO_STORE = { "Cache-Control": "private, no-store", Vary: "Cookie" };

const ref = (id: string) => createHash("sha256").update(`premium:${id}`).digest("hex").slice(0, 12);

function deny(status: number, error: string, extra: Record<string, string> = {}): Response {
  return Response.json({ error }, { status, headers: { ...NO_STORE, ...extra } });
}

type Adapter = {
  findOne: <T>(q: { model: string; where: { field: string; value: unknown }[] }) => Promise<T | null>;
  create: (q: { model: string; data: Record<string, unknown> }) => Promise<unknown>;
  update: (q: { model: string; where: { field: string; value: unknown }[]; update: Record<string, unknown> }) => Promise<unknown>;
}; // prettier-ignore

async function userLimit(userId: string, now: number) {
  const adapter = (await getAuth().$context).adapter as unknown as Adapter;
  const key = `premium:${createHash("sha256").update(userId).digest("hex")}`;
  const where = [{ field: "key", value: key }];
  const row = await adapter.findOne<LimitRow>({ model: "rateLimit", where });
  const step = limitStep(row, now);
  if (step.action === "create") {
    await adapter.create({ model: "rateLimit", data: { key, ...step.row } });
  } else if (step.ok) {
    await adapter.update({ model: "rateLimit", where, update: { ...step.row } });
  }
  return step;
}

/** `route` is the public route name for logs, e.g. "hf-current"; `apiPath` the internal path. */
export async function premiumProxy(route: string, apiPath: string): Promise<Response> {
  const v = await getViewer();
  if (!v.user || v.tier !== "premium") {
    logJson("warn", "premium refused", { route, reason: v.user ? "free" : "signed_out" });
    return deny(403, "premium_required");
  }
  let limit;
  try {
    limit = await userLimit(v.user.id, Date.now());
  } catch (err) {
    // The limit is protection, not a gate: if its table can't be reached, serve the data.
    logJson("error", "premium limit unavailable", { error: err instanceof Error ? err.message : "unknown" });
    limit = null;
  } // prettier-ignore
  if (limit && !limit.ok) {
    logJson("warn", "premium rate limited", { route, user_ref: ref(v.user.id), retry_after_s: limit.retryAfterS }); // prettier-ignore
    return deny(429, "too_many_requests", { "Retry-After": String(limit.retryAfterS) });
  }
  try {
    const res = await fetch(`${apiInternalUrl()}/api/v1/internal${apiPath}`, {
      cache: "no-store",
      headers: { "X-Internal-Token": process.env.INTERNAL_API_TOKEN ?? "" },
      signal: AbortSignal.timeout(8000),
    });
    if (res.status === 403) {
      logJson("error", "internal API refused the token", { route }); // misconfigured token
      return deny(502, "upstream_unavailable");
    }
    return new Response(await res.text(), {
      status: res.status,
      headers: { "content-type": "application/json", ...NO_STORE },
    });
  } catch {
    return deny(502, "upstream_unavailable");
  }
}

export const STATION_ID = /^K[A-Z0-9]{3}$/;
