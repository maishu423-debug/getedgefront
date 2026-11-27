import "server-only";

import type Stripe from "stripe";

import { logJson } from "@/lib/deploy";

import { entitlementFrom, trialEligible, type Entitlement } from "./entitlement";
import { CARD_BRANDS } from "./format";
import { premiumPrice, type PremiumPrice } from "./price";
import { sqlStore } from "./store";
import { billingConfig, getStripe } from "./stripe";

/** Everything the account page's subscription card shows (v2 Phase 8 B6). */
export interface AccountBilling {
  entitlement: Entitlement;
  trialEligible: boolean;
  hasCustomer: boolean;
  billingEnabled: boolean;
  price: PremiumPrice | null;
  /** Read live from Stripe for display only; never stored (we keep ids, statuses, dates). */
  card: { brand: string; last4: string } | null;
  amountDue: { amount: number; currency: string } | null;
  failedAt: Date | null;
  nextAttempt: Date | null;
}

export async function accountBilling(userId: string, now = new Date()): Promise<AccountBilling> {
  let enabled = false;
  try {
    enabled = billingConfig() !== null;
  } catch {
    enabled = false;
  }
  const store = sqlStore();
  const [subs, customer] = await Promise.all([
    store.subscriptionsOf(userId),
    store.customerOf(userId),
  ]);
  const entitlement = entitlementFrom(subs, now);
  const out: AccountBilling = {
    entitlement,
    trialEligible: trialEligible(customer?.trialUsedAt ?? null, subs),
    hasCustomer: customer !== null,
    billingEnabled: enabled,
    price: enabled ? await premiumPrice() : null,
    card: null,
    amountDue: null,
    failedAt: null,
    nextAttempt: null,
  };
  const sub = entitlement.subscription;
  if (!enabled || !sub || entitlement.tier !== "premium") return out;
  try {
    const live = await getStripe().subscriptions.retrieve(sub.id, {
      expand: ["default_payment_method", "latest_invoice"],
    });
    const pm = live.default_payment_method as Stripe.PaymentMethod | string | null;
    if (pm && typeof pm === "object" && pm.card) {
      out.card = { brand: CARD_BRANDS[pm.card.brand] ?? pm.card.brand, last4: pm.card.last4 };
    }
    const inv = live.latest_invoice as Stripe.Invoice | string | null;
    if (inv && typeof inv === "object" && inv.status === "open") {
      out.amountDue = { amount: inv.amount_due, currency: inv.currency };
      out.failedAt = inv.created ? new Date(inv.created * 1000) : null;
      out.nextAttempt = inv.next_payment_attempt ? new Date(inv.next_payment_attempt * 1000) : null;
    }
  } catch (err) {
    // The card details are a nicety: show the rest from our mirror.
    logJson("warn", "stripe subscription details unavailable", {
      error: err instanceof Error ? err.message : "unknown",
    });
  }
  return out;
}
