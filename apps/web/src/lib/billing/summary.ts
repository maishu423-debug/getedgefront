import "server-only";

import { logJson } from "@/lib/deploy";

import { entitlementFrom, trialEligible } from "./entitlement";
import { sqlStore } from "./store";
import { billingConfig } from "./stripe";
import { FREE_SUMMARY, type BillingSummary } from "./types";

export { FREE_SUMMARY, type BillingSummary };

/**
 * Computed on the server from billing.subscriptions only. If billing isn't configured or the
 * lookup fails, the user is Free (sign-in and the free site never depend on billing).
 */
export async function billingSummary(userId: string, now = new Date()): Promise<BillingSummary> {
  let enabled = false;
  try {
    enabled = billingConfig() !== null;
  } catch {
    enabled = false; // e.g. a live key without permission: billing off
  }
  try {
    const store = sqlStore();
    const [subs, customer] = await Promise.all([
      store.subscriptionsOf(userId),
      store.customerOf(userId),
    ]);
    const e = entitlementFrom(subs, now);
    const s = e.subscription;
    return {
      tier: e.tier,
      state: e.state,
      premiumUntil: e.premiumUntil?.toISOString() ?? null,
      trialEnd: s?.trialEnd?.toISOString() ?? null,
      currentPeriodEnd: s?.currentPeriodEnd?.toISOString() ?? null,
      trialEligible: trialEligible(customer?.trialUsedAt ?? null, subs),
      billingEnabled: enabled,
    };
  } catch (err) {
    logJson("error", "billing summary failed", {
      error: err instanceof Error ? err.message : "unknown",
    });
    return { ...FREE_SUMMARY, billingEnabled: false };
  }
}
