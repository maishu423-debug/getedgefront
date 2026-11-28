// Creates or verifies EdgeFront's Stripe setup (v2 Phase 8). Safe to run again: it finds what
// already exists and only creates or updates what's missing. TEST MODE ONLY until Phase 11.
//
//   STRIPE_SECRET_KEY=sk_test_... node scripts/stripe-setup.mjs \
//     [--webhook-url https://getedgefront.com/api/stripe/webhook] [--site https://getedgefront.com]
//     [--tax-code txcd_10000000]
//
// Prints the values to put in Railway (web): STRIPE_PRICE_ID, STRIPE_PORTAL_CONFIGURATION_ID and,
// only when the webhook endpoint is created, STRIPE_WEBHOOK_SECRET (Stripe shows it once).
import { readFileSync } from "node:fs";

import Stripe from "stripe";

const API_VERSION = "2026-11-18.endive"; // same as src/lib/billing/stripe.ts
const PRODUCT_KEY = "edgefront_premium";
const LOOKUP_KEY = "edgefront_premium_monthly_usd";
const AMOUNT = 2000; // $20.00 a month; change the price in Stripe, not here (see the doc)
const EVENTS = [
  "checkout.session.completed",
  "customer.subscription.created",
  "customer.subscription.updated",
  "customer.subscription.deleted",
  "customer.subscription.trial_will_end",
  "invoice.paid",
  "invoice.payment_failed",
]; // same list as src/lib/billing/stripe-mapping.ts (WEBHOOK_EVENTS)

const arg = (name) => {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 ? process.argv[i + 1] : undefined;
};
const key = process.env.STRIPE_SECRET_KEY ?? "";
if (!key.startsWith("sk_test_") && !key.startsWith("rk_test_")) {
  console.error(
    "Set STRIPE_SECRET_KEY to a TEST-mode key (sk_test_… or rk_test_…). Live mode is Phase 11.",
  );
  process.exit(2);
}
const site = (arg("site") ?? "https://getedgefront.com").replace(/\/+$/, "");
const webhookUrl = arg("webhook-url");
const stripe = new Stripe(key, { apiVersion: API_VERSION, appInfo: { name: "EdgeFront setup" } });
const out = [];

// 1. Product, with a tax code eligible for Managed Payments (Stripe as merchant of record
// requires one on every product). Default: "General – electronically supplied services";
// your accountant may prefer a SaaS code (txcd_10103000 personal use / txcd_10103001 business).
const TAX_CODE = arg("tax-code") ?? "txcd_10000000";
// Counted from the registry like the site (v2 Phase 10 fixes): Checkout shows this text.
const reg = JSON.parse(
  readFileSync(new URL("../src/generated/stations.json", import.meta.url), "utf8"),
);
const outside = reg.stations.filter((s) => s.fiveMinute === false).map((s) => s.id);
const PRODUCT_DESCRIPTION = `5-minute ASOS data for ${reg.stations.length - outside.length} of ${reg.stations.length} settlement stations${outside.length ? ` (not ${outside.join(" or ")})` : ""} and a live map of all ${reg.stations.length}.`;
const products = await stripe.products.list({ limit: 100, active: true });
let product = products.data.find((p) => p.metadata?.edgefront_key === PRODUCT_KEY);
if (product) {
  const code = typeof product.tax_code === "string" ? product.tax_code : product.tax_code?.id;
  if (code !== TAX_CODE) {
    product = await stripe.products.update(product.id, { tax_code: TAX_CODE });
    console.log(`✓ product ${product.id} "${product.name}" exists; tax code set to ${TAX_CODE}`);
  } else console.log(`✓ product ${product.id} "${product.name}" exists (tax code ${code})`);
  if (product.description !== PRODUCT_DESCRIPTION) {
    product = await stripe.products.update(product.id, { description: PRODUCT_DESCRIPTION });
    console.log(`✓ product description updated: ${PRODUCT_DESCRIPTION}`);
  }
} else {
  product = await stripe.products.create({
    name: "EdgeFront Premium",
    description: PRODUCT_DESCRIPTION,
    tax_code: TAX_CODE,
    metadata: { edgefront_key: PRODUCT_KEY },
  });
  console.log(`+ created product ${product.id} (tax code ${TAX_CODE})`);
}

// 2. Price (found by lookup key; the amount shown on the site is read from it)
const prices = await stripe.prices.list({ lookup_keys: [LOOKUP_KEY], active: true, limit: 1 });
let price = prices.data[0];
if (price) {
  const ok = price.currency === "usd" && price.recurring?.interval === "month";
  console.log(
    `✓ price ${price.id} ${price.unit_amount / 100} ${price.currency}/${price.recurring?.interval}${ok ? "" : "  ⚠ not USD monthly"}`,
  );
} else {
  price = await stripe.prices.create({
    product: product.id,
    unit_amount: AMOUNT,
    currency: "usd",
    recurring: { interval: "month" },
    lookup_key: LOOKUP_KEY,
    tax_behavior: "exclusive", // sales tax added on top when Stripe Tax collection is switched on
    nickname: "Premium monthly (USD)",
  });
  console.log(`+ created price ${price.id} $${AMOUNT / 100}/month`);
}
out.push(`STRIPE_PRICE_ID=${price.id}`);

// 3. Customer Portal: update card, invoices, cancel at period end; no plan or quantity changes
const portalFeatures = {
  customer_update: { enabled: false }, // the email is the account's; changed in EdgeFront only
  invoice_history: { enabled: true },
  payment_method_update: { enabled: true },
  subscription_cancel: {
    enabled: true,
    mode: "at_period_end",
    proration_behavior: "none",
    cancellation_reason: { enabled: false }, // owner: no "why are you cancelling?" question
  },
  subscription_update: { enabled: false }, // no plan switching, no quantity changes
};
const portalBody = {
  business_profile: {
    headline: "EdgeFront: manage your Premium subscription",
    privacy_policy_url: `${site}/privacy`,
    terms_of_service_url: `${site}/terms`,
  },
  default_return_url: `${site}/account`,
  features: portalFeatures,
  metadata: { edgefront_key: "portal" },
};
const configs = await stripe.billingPortal.configurations.list({ active: true, limit: 100 });
let portal = configs.data.find((c) => c.metadata?.edgefront_key === "portal");
if (portal) {
  portal = await stripe.billingPortal.configurations.update(portal.id, portalBody);
  console.log(`✓ portal configuration ${portal.id} updated`);
} else {
  portal = await stripe.billingPortal.configurations.create(portalBody);
  console.log(`+ created portal configuration ${portal.id}`);
}
out.push(`STRIPE_PORTAL_CONFIGURATION_ID=${portal.id}`);

// 4. Webhook endpoint (production URL; local development uses the Stripe CLI instead)
if (webhookUrl) {
  const endpoints = await stripe.webhookEndpoints.list({ limit: 100 });
  const existing = endpoints.data.find((e) => e.url === webhookUrl);
  if (existing) {
    await stripe.webhookEndpoints.update(existing.id, { enabled_events: EVENTS, disabled: false });
    console.log(
      `✓ webhook ${existing.id} → ${webhookUrl} (events updated, API ${existing.api_version})`,
    );
    console.log("  Its signing secret was shown when it was created; Stripe can't show it again.");
    console.log("  Lost it? Dashboard → Developers → Webhooks → the endpoint → Roll secret.");
  } else {
    const created = await stripe.webhookEndpoints.create({
      url: webhookUrl,
      enabled_events: EVENTS,
      api_version: API_VERSION,
      description: "EdgeFront web (billing mirror)",
    });
    console.log(`+ created webhook ${created.id} → ${webhookUrl}`);
    out.push(`STRIPE_WEBHOOK_SECRET=${created.secret}   # shown only now: put it in Railway`);
  }
}

console.log("\nPut these in Railway → web → Variables (test mode):");
for (const line of out) console.log(`  ${line}`);
console.log("  STRIPE_SECRET_KEY=<your sk_test_ key>   STRIPE_TAX_ENABLED=false");
