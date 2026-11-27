/**
 * Entitlement (v2 Phase 8, CONTEXT V2.4): who is Premium, computed on the server from the
 * subscriptions Stripe last reported (billing.subscriptions), never from anything the browser
 * sends. Pure, so every status × time combination is unit-tested.
 *
 * - trialing, active                → Premium
 * - past_due                        → Premium while Stripe retries (shown with a banner)
 * - cancel at period end / cancel_at → Premium until that moment, then Free
 * - canceled, unpaid, incomplete, incomplete_expired, paused, none → Free
 */

export type Tier = "free" | "premium";

/** What the account page and the header show. */
export type BillingState = "trialing" | "active" | "past_due" | "canceling" | "free";

export interface SubscriptionSnapshot {
  id: string;
  status: string;
  priceId: string | null;
  currentPeriodEnd: Date | null;
  cancelAtPeriodEnd: boolean;
  cancelAt: Date | null;
  trialEnd: Date | null;
  canceledAt: Date | null;
  endedAt: Date | null;
  latestInvoiceStatus: string | null;
}

export interface Entitlement {
  tier: Tier;
  state: BillingState;
  /** The subscription the state describes (the one granting Premium, else the latest one). */
  subscription: SubscriptionSnapshot | null;
  /** When Premium ends if nothing changes (cancellation date), else null. */
  premiumUntil: Date | null;
}

const FREE: Entitlement = { tier: "free", state: "free", subscription: null, premiumUntil: null };

/** When a subscription that is set to stop will stop, or null if it renews. */
function scheduledEnd(s: SubscriptionSnapshot): Date | null {
  if (s.cancelAtPeriodEnd) return s.currentPeriodEnd ?? s.cancelAt;
  return s.cancelAt;
}

/** One subscription → entitlement, at `now`. */
export function entitlementOf(s: SubscriptionSnapshot, now: Date): Entitlement {
  const end = scheduledEnd(s);
  const before = (d: Date | null) => d !== null && now.getTime() < d.getTime();
  switch (s.status) {
    case "trialing":
    case "active":
      if (end) {
        // Set to cancel: Premium until then (even if the "canceled" webhook is late).
        return before(end)
          ? { tier: "premium", state: "canceling", subscription: s, premiumUntil: end }
          : { ...FREE, subscription: s };
      }
      return { tier: "premium", state: s.status, subscription: s, premiumUntil: null };
    case "past_due":
      // Stripe is retrying the payment; access continues until it gives up.
      return { tier: "premium", state: "past_due", subscription: s, premiumUntil: end };
    case "canceled":
      // Cancelled at period end and the period isn't over yet (clock skew, early event).
      if (s.cancelAtPeriodEnd && before(s.currentPeriodEnd) && !s.endedAt) {
        return {
          tier: "premium",
          state: "canceling",
          subscription: s,
          premiumUntil: s.currentPeriodEnd,
        };
      }
      return { ...FREE, subscription: s };
    default: // unpaid, incomplete, incomplete_expired, paused, unknown
      return { ...FREE, subscription: s };
  }
}

const RANK: Record<BillingState, number> = {
  active: 4,
  trialing: 3,
  past_due: 2,
  canceling: 1,
  free: 0,
};

/** A user's subscriptions → their entitlement: the best Premium one, else Free. */
export function entitlementFrom(subs: SubscriptionSnapshot[], now: Date): Entitlement {
  if (!subs.length) return FREE;
  const all = subs.map((s) => entitlementOf(s, now));
  const premium = all.filter((e) => e.tier === "premium");
  if (premium.length) {
    return premium.sort((a, b) => RANK[b.state] - RANK[a.state])[0]!;
  }
  // Free: describe the most recently ended/created subscription (for "Subscribe" wording).
  const latest = [...subs].sort(
    (a, b) => (b.endedAt ?? b.canceledAt ?? b.currentPeriodEnd ?? new Date(0)).getTime() -
      (a.endedAt ?? a.canceledAt ?? a.currentPeriodEnd ?? new Date(0)).getTime(),
  )[0]!; // prettier-ignore
  return { ...FREE, subscription: latest };
}

/**
 * One free trial per account: eligible only if the account never had a trial (recorded when a
 * trialing subscription is first mirrored, and visible on any past subscription's trial_end).
 * Card fingerprints are deliberately not used (owner decision).
 */
export function trialEligible(
  trialUsedAt: Date | null,
  subs: Pick<SubscriptionSnapshot, "trialEnd">[],
): boolean {
  return trialUsedAt === null && subs.every((s) => s.trialEnd === null);
}

export const TRIAL_DAYS = 7;

/**
 * Our own reminder email goes out when Stripe sends customer.subscription.trial_will_end, which
 * Stripe fires this many days before the trial ends (Dashboard: Billing settings, "Trial ending
 * events"; default 3). The pricing page quotes this number, so keep them equal.
 */
export const TRIAL_REMINDER_DAYS = 3;
