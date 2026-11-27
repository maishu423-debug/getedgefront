import type Stripe from "stripe";

import { getAuth, siteUrl } from "@/lib/auth/server";
import { sendEmail } from "@/lib/auth/email";
import * as T from "@/lib/auth/templates";
import { formatDay, formatMoney } from "@/lib/billing/format";
import { json } from "@/lib/billing/http";
import { sqlStore } from "@/lib/billing/store";
import { billingConfig, getStripe } from "@/lib/billing/stripe";
import { handleEvent } from "@/lib/billing/webhook";
import { logJson } from "@/lib/deploy";

/**
 * Stripe webhook (v2 Phase 8). The signature is checked against the raw body with
 * STRIPE_WEBHOOK_SECRET; anything unsigned or tampered with is refused. Each event is handled
 * once; the subscription is re-fetched and mirrored. Logs carry event ids only.
 */
export async function POST(req: Request) {
  let config;
  try {
    config = billingConfig();
  } catch {
    config = null;
  }
  if (!config?.webhookSecret) return json({ error: "billing not configured" }, 503);

  const signature = req.headers.get("stripe-signature");
  if (!signature) return json({ error: "missing signature" }, 400);
  const raw = await req.text(); // the exact bytes Stripe signed
  let event: Stripe.Event;
  try {
    event = getStripe().webhooks.constructEvent(raw, signature, config.webhookSecret);
  } catch {
    logJson("warn", "stripe webhook rejected: bad signature", {});
    return json({ error: "invalid signature" }, 400);
  }

  const outcome = await handleEvent(event, {
    store: sqlStore(),
    fetchSubscription: (id) =>
      getStripe().subscriptions.retrieve(id, { expand: ["latest_invoice"] }),
    onTrialWillEnd: async (userId, sub) => {
      const ctx = await getAuth().$context;
      const user = await ctx.internalAdapter.findUserById(userId);
      const price = sub.items.data[0]?.price;
      if (!user || !sub.trial_end || price?.unit_amount == null) return;
      await sendEmail(
        T.trialEnding(
          user.email,
          formatDay(new Date(sub.trial_end * 1000), "UTC"),
          formatMoney(price.unit_amount, price.currency),
          `${siteUrl()}/account`,
        ),
      );
    },
  });

  if (outcome.result === "error") {
    logJson("error", "stripe webhook failed", {
      event_id: event.id,
      type: event.type,
      error: outcome.message,
    });
    return json({ error: "processing failed" }, 500); // Stripe retries
  }
  logJson("info", "stripe webhook", {
    event_id: event.id,
    type: event.type,
    result: outcome.result,
  });
  return json({ received: true });
}
