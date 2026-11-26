import "server-only";

import { headers } from "next/headers";
import { connection } from "next/server";

import { getAuth } from "./server";

export type Tier = "anonymous" | "free" | "premium";

export interface ViewerUser {
  id: string;
  name: string;
  email: string;
  emailVerified: boolean;
}

export interface Viewer {
  user: ViewerUser | null;
  tier: Tier;
  /** When the current session was created. */
  sessionCreatedAt: Date | null;
  /** Signed in within the last 10 minutes (Better Auth session.freshAge): enough to delete the
   * account without re-entering a password. */
  fresh: boolean;
}

export const FRESH_MS = 10 * 60 * 1000;

/** Pure part, unit-tested: session → viewer. Phase 8 adds entitlement (premium). */
export function viewerFromSession(
  session: { user: ViewerUser; session: { createdAt: Date | string } } | null,
  nowMs: number,
): Viewer {
  if (!session) return { user: null, tier: "anonymous", sessionCreatedAt: null, fresh: false };
  const { id, name, email, emailVerified } = session.user;
  return {
    user: { id, name, email, emailVerified },
    tier: "free", // never "premium" before Phase 8 billing
    sessionCreatedAt: new Date(session.session.createdAt),
    fresh: nowMs - new Date(session.session.createdAt).getTime() < FRESH_MS,
  };
}

/** The signed-in user (or none) for this request, checked on the server. */
export async function getViewer(): Promise<Viewer> {
  // First, before any database access or clock read: request time only. headers() alone still
  // allows a (partial) prefetch render, where Date.now() — used here and inside Better Auth's
  // session check — is refused.
  await connection();
  const h = await headers();
  const session = await getAuth().api.getSession({ headers: h });
  return viewerFromSession(session, Date.now());
}
