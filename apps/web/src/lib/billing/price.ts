import "server-only";

import { logJson } from "@/lib/deploy";

import { billingConfig, getStripe } from "./stripe";

/** The Premium price as Stripe has it (the amount is never hard-coded). */
export interface PremiumPrice {
  id: string;
  unitAmount: number; // smallest currency unit (cents)
  currency: string; // "usd"
  interval: string; // "month"
}

const TTL_MS = 10 * 60 * 1000;
let cached: { value: PremiumPrice | null; at: number } | null = null;

/**
 * Read from Stripe's Price object (STRIPE_PRICE_ID) and cached for 10 minutes, so changing the
 * price in Stripe updates the site with no code change. Null when unavailable: the UI then says
 * so instead of showing a made-up amount.
 */
export async function premiumPrice(nowMs = Date.now()): Promise<PremiumPrice | null> {
  if (cached && nowMs - cached.at < TTL_MS) return cached.value;
  let value: PremiumPrice | null = null;
  try {
    const config = billingConfig();
    if (config) {
      const p = await getStripe().prices.retrieve(config.priceId);
      if (p.active && p.unit_amount != null && p.recurring) {
        value = {
          id: p.id,
          unitAmount: p.unit_amount,
          currency: p.currency,
          interval: p.recurring.interval,
        };
      }
    }
  } catch (err) {
    logJson("error", "stripe price lookup failed", {
      error: err instanceof Error ? err.message : "unknown",
    });
    // keep a stale value rather than nothing, but retry soon
    if (cached?.value) return cached.value;
  }
  cached = { value, at: nowMs };
  return value;
}
