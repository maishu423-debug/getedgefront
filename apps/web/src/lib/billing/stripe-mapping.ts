import type Stripe from "stripe";

import { TRIAL_DAYS, type SubscriptionSnapshot } from "./entitlement";

/**
 * Pure translations between Stripe objects and ours (v2 Phase 8), unit-tested.
 * API version 2026-11-18.endive: billing periods live on subscription items
 * (`items.data[].current_period_end`), not on the subscription.
 */

const date = (unix: number | null | undefined) => (unix ? new Date(unix * 1000) : null);

export const stripeId = (v: string | { id: string } | null | undefined) =>
  v == null ? null : typeof v === "string" ? v : v.id;

/** Our mirror of a subscription as Stripe reports it now. */
export function snapshotFromStripe(sub: Stripe.Subscription): SubscriptionSnapshot & {
  customerId: string;
  userIdFromMetadata: string | null;
} {
  const items = sub.items?.data ?? [];
  const periodEnds = items.map((i) => i.current_period_end).filter((n): n is number => !!n);
  const invoice = sub.latest_invoice;
  return {
    id: sub.id,
    customerId: stripeId(sub.customer)!,
    userIdFromMetadata: sub.metadata?.user_id || null,
    status: sub.status,
    priceId: items[0]?.price?.id ?? null,
    currentPeriodEnd: periodEnds.length ? date(Math.max(...periodEnds)) : null,
    cancelAtPeriodEnd: Boolean(sub.cancel_at_period_end),
    cancelAt: date(sub.cancel_at),
    trialEnd: date(sub.trial_end),
    canceledAt: date(sub.canceled_at),
    endedAt: date(sub.ended_at),
    latestInvoiceStatus: invoice && typeof invoice === "object" ? (invoice.status ?? null) : null,
  };
}

/**
 * The subscription an event is about (we re-fetch it and mirror its current state, so events
 * arriving out of order or twice can't leave a stale row). Null: not a subscription event.
 */
export function subscriptionIdOf(event: Stripe.Event): string | null {
  const obj = event.data.object as unknown as Record<string, unknown>;
  switch (event.type) {
    case "checkout.session.completed": {
      const s = obj as unknown as Stripe.Checkout.Session;
      return s.mode === "subscription" ? stripeId(s.subscription) : null;
    }
    case "customer.subscription.created":
    case "customer.subscription.updated":
    case "customer.subscription.deleted":
    case "customer.subscription.trial_will_end":
    case "customer.subscription.paused":
    case "customer.subscription.resumed":
      return (obj as { id?: string }).id ?? null;
    case "invoice.paid":
    case "invoice.payment_failed": {
      const inv = obj as unknown as Stripe.Invoice & { subscription?: string | { id: string } };
      return (
        stripeId(inv.parent?.subscription_details?.subscription) ??
        stripeId(inv.subscription) ??
        null
      );
    }
    default:
      return null;
  }
}

/** The events the webhook endpoint is subscribed to (setup script + docs use this list). */
export const WEBHOOK_EVENTS = [
  "checkout.session.completed",
  "customer.subscription.created",
  "customer.subscription.updated",
  "customer.subscription.deleted",
  "customer.subscription.trial_will_end",
  "invoice.paid",
  "invoice.payment_failed",
] as const;

export interface CheckoutInput {
  customerId: string;
  userId: string;
  priceId: string;
  withTrial: boolean;
  siteUrl: string;
  taxEnabled: boolean;
  /** Stripe as merchant of record (it then handles tax itself). */
  managedPayments?: boolean;
}

/**
 * Checkout Session parameters (subscription mode, card always collected, 7-day trial only for
 * accounts that never had one). Free trial via the stable `subscription_data.trial_period_days`
 * ("trial offers" are a private preview in Checkout as of 2026-11).
 */
export function checkoutSessionParams(i: CheckoutInput): Stripe.Checkout.SessionCreateParams {
  return {
    mode: "subscription",
    customer: i.customerId,
    client_reference_id: i.userId,
    line_items: [{ price: i.priceId, quantity: 1 }],
    payment_method_collection: "always",
    success_url: `${i.siteUrl}/account?checkout=success`,
    cancel_url: `${i.siteUrl}/pricing?checkout=cancelled`,
    // Who sells: EdgeFront (default; Stripe Tax only if STRIPE_TAX_ENABLED) or, if the owner
    // turns it on, Stripe as merchant of record (Managed Payments), which handles tax itself.
    // Stated explicitly because Stripe accounts can default to Managed Payments.
    ...(i.managedPayments
      ? { managed_payments: { enabled: true } }
      : {
          managed_payments: { enabled: false },
          automatic_tax: { enabled: i.taxEnabled },
          // With tax on, Checkout needs the customer's address and may save it on the customer.
          ...(i.taxEnabled ? { customer_update: { address: "auto" as const } } : {}),
        }),
    metadata: { user_id: i.userId },
    subscription_data: {
      metadata: { user_id: i.userId },
      ...(i.withTrial
        ? {
            trial_period_days: TRIAL_DAYS,
            trial_settings: { end_behavior: { missing_payment_method: "cancel" as const } },
          }
        : {}),
    },
  };
}
