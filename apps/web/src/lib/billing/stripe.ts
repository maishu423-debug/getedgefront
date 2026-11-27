import "server-only";

import Stripe from "stripe";

/**
 * Stripe client (v2 Phase 8). The API version is pinned here (stripe-node 23.2.0 ships with the
 * same version), so a Stripe account default change can't alter what we receive.
 */
export const STRIPE_API_VERSION = "2026-11-18.endive" as const;

export interface BillingConfig {
  secretKey: string;
  webhookSecret: string;
  priceId: string;
  taxEnabled: boolean;
  /** Stripe Managed Payments (Stripe as merchant of record). Off unless the owner decides. */
  managedPayments: boolean;
  portalConfigurationId: string | null;
}

/**
 * Billing settings from the environment, or null when billing isn't configured (the site then
 * behaves as before: no checkout, everyone Free). Live keys are refused until the owner allows
 * them (Phase 11): production runs on Stripe test mode, so nobody can pay real money yet.
 */
export function billingConfig(
  env: Record<string, string | undefined> = process.env,
): BillingConfig | null {
  const secretKey = env.STRIPE_SECRET_KEY ?? "";
  const priceId = env.STRIPE_PRICE_ID ?? "";
  if (!secretKey || !priceId) return null;
  // secret (sk_) and restricted (rk_) live keys alike
  if (/^(sk|rk)_live_/.test(secretKey) && env.STRIPE_ALLOW_LIVE !== "true") {
    throw new Error(
      "Live Stripe keys are not allowed yet (set STRIPE_ALLOW_LIVE=true in Phase 11)",
    );
  }
  return {
    secretKey,
    webhookSecret: env.STRIPE_WEBHOOK_SECRET ?? "",
    priceId,
    taxEnabled: env.STRIPE_TAX_ENABLED === "true",
    managedPayments: env.STRIPE_MANAGED_PAYMENTS === "true",
    portalConfigurationId: env.STRIPE_PORTAL_CONFIGURATION_ID || null,
  };
}

/**
 * The end-to-end fake Stripe (e2e/fake-stripe.mjs) is only accepted on localhost and never on
 * Railway; anything else stops the server.
 */
export function e2eFakeStripeUrl(env: Record<string, string | undefined> = process.env) {
  const url = env.E2E_FAKE_STRIPE_URL;
  if (!url) return null;
  const host = URL.canParse(url) ? new URL(url).hostname : "";
  if (env.RAILWAY_ENVIRONMENT_NAME || !["localhost", "127.0.0.1"].includes(host)) {
    throw new Error("E2E_FAKE_STRIPE_URL is for local end-to-end tests only");
  }
  return new URL(url);
}

let client: Stripe | null = null;

export function getStripe(): Stripe {
  if (client) return client;
  const config = billingConfig();
  if (!config) throw new Error("Stripe is not configured (STRIPE_SECRET_KEY, STRIPE_PRICE_ID)");
  const fake = e2eFakeStripeUrl();
  client = new Stripe(config.secretKey, {
    apiVersion: STRIPE_API_VERSION,
    maxNetworkRetries: 2,
    timeout: 20_000,
    appInfo: { name: "EdgeFront", url: "https://getedgefront.com" },
    telemetry: false,
    ...(fake
      ? {
          host: fake.hostname,
          port: Number(fake.port || 80),
          protocol: fake.protocol.replace(":", "") as "http" | "https",
        }
      : {}),
  });
  return client;
}
