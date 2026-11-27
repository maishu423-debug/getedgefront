"use client";

import { authClient, reloadTo } from "@/lib/auth/client";

import { FREE_SUMMARY, type BillingSummary } from "./types";

/**
 * Browser side of billing (v2 Phase 8). The plan shown here comes from the session, which the
 * server computes from billing.subscriptions; the browser never decides anything.
 */
export function useBilling(): {
  isPending: boolean;
  signedIn: boolean;
  emailVerified: boolean;
  email: string;
  billing: BillingSummary;
} {
  const { data, isPending } = authClient.useSession();
  const session = data as (typeof data & { billing?: BillingSummary }) | null;
  return {
    isPending,
    signedIn: Boolean(session?.user),
    emailVerified: Boolean(session?.user?.emailVerified),
    email: session?.user?.email ?? "",
    billing: session?.billing ?? FREE_SUMMARY,
  };
}

export type BillingActionError =
  | "signed_out"
  | "email_unverified"
  | "already_premium"
  | "billing_unavailable"
  | "no_customer"
  | "failed";

async function post(path: string, body: unknown): Promise<{ url?: string; code?: string }> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  return (await res.json().catch(() => ({}))) as { url?: string; code?: string };
}

/** Starts Stripe Checkout; navigates there, or returns why it couldn't. */
export async function startCheckout(): Promise<BillingActionError | null> {
  try {
    // a new idempotency key per click: a double click can't create two sessions
    const out = await post("/api/billing/checkout", { clickId: crypto.randomUUID() });
    if (out.url) {
      window.location.assign(out.url);
      return null;
    }
    if (out.code === "signed_out") {
      reloadTo("/signin?next=%2Fpricing");
      return null;
    }
    if (out.code === "already_premium") {
      reloadTo("/account");
      return null;
    }
    return (out.code as BillingActionError) ?? "failed";
  } catch {
    return "failed";
  }
}

/** Opens the Stripe Customer Portal (update card, invoices, cancel or resume). */
export async function openPortal(): Promise<BillingActionError | null> {
  try {
    const out = await post("/api/billing/portal", {});
    if (out.url) {
      window.location.assign(out.url);
      return null;
    }
    return (out.code as BillingActionError) ?? "failed";
  } catch {
    return "failed";
  }
}

export const BILLING_ERRORS: Record<BillingActionError, string> = {
  signed_out: "Please sign in first.",
  email_unverified: "Confirm your email address first: we sent you a link.",
  already_premium: "You're already on Premium.",
  billing_unavailable: "Subscriptions aren't available right now. Please try again later.",
  no_customer: "There's no billing account yet.",
  failed: "Something went wrong reaching our payment page. Please try again.",
};
