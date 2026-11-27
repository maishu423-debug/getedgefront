/** Billing types shared by server and browser code (no secrets, no server imports). */

import type { BillingState, Tier } from "./entitlement";

/** What the session (header, pricing CTA) and getViewer know about a user's billing. */
export interface BillingSummary {
  tier: Tier;
  state: BillingState;
  /** ISO: Premium ends then (cancellation scheduled). */
  premiumUntil: string | null;
  /** ISO: end of the trial (trialing) or of the current period (next payment). */
  trialEnd: string | null;
  currentPeriodEnd: string | null;
  trialEligible: boolean;
  /** Stripe is configured on this server (else checkout is unavailable). */
  billingEnabled: boolean;
}

export const FREE_SUMMARY: BillingSummary = {
  tier: "free",
  state: "free",
  premiumUntil: null,
  trialEnd: null,
  currentPeriodEnd: null,
  trialEligible: true,
  billingEnabled: false,
};
