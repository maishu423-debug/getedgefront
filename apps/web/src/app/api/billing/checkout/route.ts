import { siteUrl } from "@/lib/auth/server";
import { getViewer } from "@/lib/auth/viewer";
import { trialEligible } from "@/lib/billing/entitlement";
import { fromOurSite, json } from "@/lib/billing/http";
import { sqlStore } from "@/lib/billing/store";
import { billingConfig, getStripe } from "@/lib/billing/stripe";
import { checkoutSessionParams } from "@/lib/billing/stripe-mapping";
import { logJson } from "@/lib/deploy";

/**
 * Starts Stripe Checkout for Premium (v2 Phase 8). Created on the server only: the price comes
 * from STRIPE_PRICE_ID, the customer is the user's own (created once), the trial is given only
 * to accounts that never had one, and each click has its own idempotency key.
 */
export async function POST(req: Request) {
  if (!fromOurSite(req)) return json({ code: "bad_origin" }, 403);
  let config;
  try {
    config = billingConfig();
  } catch {
    config = null;
  }
  if (!config) return json({ code: "billing_unavailable" }, 503);

  const viewer = await getViewer();
  const user = viewer.user;
  if (!user) return json({ code: "signed_out" }, 401);
  if (!user.emailVerified) return json({ code: "email_unverified" }, 403);
  if (viewer.tier === "premium") return json({ code: "already_premium" }, 409);

  const body = (await req.json().catch(() => ({}))) as { clickId?: unknown };
  const clickId = typeof body.clickId === "string" ? body.clickId : "";
  if (!/^[A-Za-z0-9-]{8,64}$/.test(clickId)) return json({ code: "bad_request" }, 400);

  try {
    const stripe = getStripe();
    const store = sqlStore();
    const existing = await store.customerOf(user.id);
    let customerId = existing?.stripeCustomerId;
    if (!customerId) {
      const created = await stripe.customers.create(
        { email: user.email, name: user.name || undefined, metadata: { user_id: user.id } },
        { idempotencyKey: `customer:${user.id}` },
      );
      customerId = await store.saveCustomer(user.id, created.id);
    }
    const subs = await store.subscriptionsOf(user.id);
    const session = await stripe.checkout.sessions.create(
      checkoutSessionParams({
        customerId,
        userId: user.id,
        priceId: config.priceId,
        withTrial: trialEligible(existing?.trialUsedAt ?? null, subs),
        siteUrl: siteUrl(),
        taxEnabled: config.taxEnabled,
        managedPayments: config.managedPayments,
      }),
      { idempotencyKey: `checkout:${user.id}:${clickId}` },
    );
    if (!session.url) throw new Error("checkout session has no url");
    return json({ url: session.url });
  } catch (err) {
    logJson("error", "checkout session failed", {
      error: err instanceof Error ? err.message : "unknown",
    });
    return json({ code: "stripe_error" }, 502);
  }
}
