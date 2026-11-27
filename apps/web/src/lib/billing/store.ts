import "server-only";

import { billingDb, dbBool, iso, toBool, toDate } from "./db";
import type { SubscriptionSnapshot } from "./entitlement";

/** Billing persistence (v2 Phase 8). An interface so webhook handling is unit-tested in memory. */
export interface BillingStore {
  customerOf(userId: string): Promise<{ stripeCustomerId: string; trialUsedAt: Date | null } | null>;
  userOfCustomer(stripeCustomerId: string): Promise<string | null>;
  /** Insert if absent; returns the stored customer id (the first writer wins). */
  saveCustomer(userId: string, stripeCustomerId: string): Promise<string>;
  subscriptionsOf(userId: string): Promise<SubscriptionSnapshot[]>;
  saveSubscription(userId: string, customerId: string, s: SubscriptionSnapshot, eventId: string | null): Promise<void>;
  markTrialUsed(userId: string, at: Date): Promise<void>;
  /** Records an event id; "processed" if it was already handled. */
  beginEvent(id: string, type: string): Promise<"new" | "processed">;
  finishEvent(id: string, error: string | null): Promise<void>;
} // prettier-ignore

const now = () => new Date().toISOString();

export function sqlStore(): BillingStore {
  const { db } = billingDb();
  return {
    async customerOf(userId) {
      const r = await db
        .selectFrom("customers")
        .select(["stripe_customer_id", "trial_used_at"])
        .where("user_id", "=", userId)
        .executeTakeFirst();
      return r ? { stripeCustomerId: r.stripe_customer_id, trialUsedAt: toDate(r.trial_used_at) } : null;
    },
    async userOfCustomer(stripeCustomerId) {
      const r = await db
        .selectFrom("customers")
        .select("user_id")
        .where("stripe_customer_id", "=", stripeCustomerId)
        .executeTakeFirst();
      return r?.user_id ?? null;
    },
    async saveCustomer(userId, stripeCustomerId) {
      await db
        .insertInto("customers")
        .values({ user_id: userId, stripe_customer_id: stripeCustomerId, trial_used_at: null, created_at: now() })
        .onConflict((oc) => oc.column("user_id").doNothing())
        .execute();
      const r = await db.selectFrom("customers").select("stripe_customer_id").where("user_id", "=", userId).executeTakeFirstOrThrow();
      return r.stripe_customer_id;
    },
    async subscriptionsOf(userId) {
      const rows = await db.selectFrom("subscriptions").selectAll().where("user_id", "=", userId).execute();
      return rows.map((r) => ({
        id: r.stripe_subscription_id,
        status: r.status,
        priceId: r.price_id,
        currentPeriodEnd: toDate(r.current_period_end),
        cancelAtPeriodEnd: toBool(r.cancel_at_period_end),
        cancelAt: toDate(r.cancel_at),
        trialEnd: toDate(r.trial_end),
        canceledAt: toDate(r.canceled_at),
        endedAt: toDate(r.ended_at),
        latestInvoiceStatus: r.latest_invoice_status,
      }));
    },
    async saveSubscription(userId, customerId, s, eventId) {
      const row = {
        user_id: userId,
        stripe_customer_id: customerId,
        status: s.status,
        price_id: s.priceId,
        current_period_end: iso(s.currentPeriodEnd),
        cancel_at_period_end: dbBool(s.cancelAtPeriodEnd),
        cancel_at: iso(s.cancelAt),
        trial_end: iso(s.trialEnd),
        canceled_at: iso(s.canceledAt),
        ended_at: iso(s.endedAt),
        latest_invoice_status: s.latestInvoiceStatus,
        updated_from_event_id: eventId,
        updated_at: now(),
      };
      await db
        .insertInto("subscriptions")
        .values({ stripe_subscription_id: s.id, ...row })
        .onConflict((oc) => oc.column("stripe_subscription_id").doUpdateSet(row))
        .execute();
    },
    async markTrialUsed(userId, at) {
      await db
        .updateTable("customers")
        .set({ trial_used_at: at.toISOString() })
        .where("user_id", "=", userId)
        .where("trial_used_at", "is", null)
        .execute();
    },
    async beginEvent(id, type) {
      await db
        .insertInto("webhook_events")
        .values({ stripe_event_id: id, type, received_at: now(), processed_at: null, error: null })
        .onConflict((oc) => oc.column("stripe_event_id").doNothing())
        .execute();
      const r = await db.selectFrom("webhook_events").select("processed_at").where("stripe_event_id", "=", id).executeTakeFirstOrThrow();
      return r.processed_at ? "processed" : "new";
    },
    async finishEvent(id, error) {
      await db
        .updateTable("webhook_events")
        .set(error ? { error: error.slice(0, 500) } : { processed_at: now(), error: null })
        .where("stripe_event_id", "=", id)
        .execute();
    },
  };
} // prettier-ignore
