import type Stripe from "stripe";

import type { BillingStore } from "./store";
import { snapshotFromStripe, subscriptionIdOf } from "./stripe-mapping";

/**
 * Webhook handling (v2 Phase 8), independent of HTTP so it is unit-tested with an in-memory
 * store and a fake Stripe:
 * - each event id is handled once (billing.webhook_events);
 * - the subscription is re-fetched from Stripe and its *current* state mirrored, so events that
 *   arrive late, out of order or twice can't leave an old state behind;
 * - errors are returned (logged by the caller with the event id only) and the event stays
 *   unprocessed, so Stripe's retry handles it again.
 */

export interface WebhookDeps {
  store: BillingStore;
  fetchSubscription: (id: string) => Promise<Stripe.Subscription>;
  /** Optional side effects, e.g. our own trial reminder email. */
  onTrialWillEnd?: (userId: string, sub: Stripe.Subscription) => Promise<void>;
}

export type WebhookOutcome =
  | { result: "duplicate" }
  | { result: "ignored" } // not an event we act on
  | { result: "no_user" } // e.g. the account was deleted; nothing to mirror
  | { result: "mirrored"; userId: string; status: string }
  | { result: "error"; message: string };

export async function handleEvent(event: Stripe.Event, deps: WebhookDeps): Promise<WebhookOutcome> {
  if ((await deps.store.beginEvent(event.id, event.type)) === "processed") {
    return { result: "duplicate" };
  }
  try {
    const outcome = await mirror(event, deps);
    await deps.store.finishEvent(event.id, null);
    return outcome;
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    await deps.store.finishEvent(event.id, message);
    return { result: "error", message };
  }
}

async function mirror(event: Stripe.Event, deps: WebhookDeps): Promise<WebhookOutcome> {
  const subId = subscriptionIdOf(event);
  if (!subId) return { result: "ignored" };
  const sub = await deps.fetchSubscription(subId);
  const snap = snapshotFromStripe(sub);

  // Which account: our customer mapping first, then the user id we put in the metadata.
  let userId = await deps.store.userOfCustomer(snap.customerId);
  if (!userId && snap.userIdFromMetadata) {
    try {
      const saved = await deps.store.saveCustomer(snap.userIdFromMetadata, snap.customerId);
      if (saved === snap.customerId) userId = snap.userIdFromMetadata;
    } catch {
      userId = null; // the account no longer exists (foreign key)
    }
  }
  if (!userId) return { result: "no_user" };

  await deps.store.saveSubscription(userId, snap.customerId, snap, event.id);
  if (snap.trialEnd) await deps.store.markTrialUsed(userId, new Date(event.created * 1000));
  if (event.type === "customer.subscription.trial_will_end" && snap.status === "trialing") {
    await deps.onTrialWillEnd?.(userId, sub);
  }
  return { result: "mirrored", userId, status: snap.status };
}
