import Stripe from "stripe";
import { describe, expect, it, vi } from "vitest";

import {
  entitlementFrom,
  entitlementOf,
  trialEligible,
  type SubscriptionSnapshot,
} from "./entitlement";
import { checkoutAllowed, parseAllowlist, testModeGate } from "./allowlist";
import { formatDay, formatMoney } from "./format";
import type { BillingStore } from "./store";
import { billingConfig, e2eFakeStripeUrl, STRIPE_API_VERSION } from "./stripe";
import {
  checkoutSessionParams,
  snapshotFromStripe,
  subscriptionIdOf,
  WEBHOOK_EVENTS,
} from "./stripe-mapping";
import { handleEvent } from "./webhook";

vi.mock("server-only", () => ({}));

const NOW = new Date("2026-12-01T12:00:00Z");
const day = (n: number) => new Date(NOW.getTime() + n * 86_400_000);

function sub(over: Partial<SubscriptionSnapshot> = {}): SubscriptionSnapshot {
  return {
    id: "sub_1",
    status: "active",
    priceId: "price_1",
    currentPeriodEnd: day(20),
    cancelAtPeriodEnd: false,
    cancelAt: null,
    trialEnd: null,
    canceledAt: null,
    endedAt: null,
    latestInvoiceStatus: "paid",
    ...over,
  };
}

// ------------------------------------------------------------------ entitlement

describe("entitlement: every status × time", () => {
  const cases: [string, Partial<SubscriptionSnapshot>, "premium" | "free", string][] = [
    ["trialing", { status: "trialing", trialEnd: day(5), currentPeriodEnd: day(5) }, "premium", "trialing"],
    ["active", { status: "active" }, "premium", "active"],
    ["past_due (Stripe retrying)", { status: "past_due", latestInvoiceStatus: "open" }, "premium", "past_due"],
    ["active, cancel at period end, before the end", { cancelAtPeriodEnd: true }, "premium", "canceling"],
    ["active, cancel at period end, after the end (late webhook)", { cancelAtPeriodEnd: true, currentPeriodEnd: day(-1) }, "free", "free"],
    ["trialing, cancel at period end, before trial end", { status: "trialing", cancelAtPeriodEnd: true, currentPeriodEnd: day(3), trialEnd: day(3) }, "premium", "canceling"],
    ["active, cancel_at in the future", { cancelAt: day(4) }, "premium", "canceling"],
    ["active, cancel_at passed", { cancelAt: day(-2) }, "free", "free"],
    ["canceled with cancel_at_period_end, period not over", { status: "canceled", cancelAtPeriodEnd: true, currentPeriodEnd: day(1) }, "premium", "canceling"],
    ["canceled with cancel_at_period_end, period over", { status: "canceled", cancelAtPeriodEnd: true, currentPeriodEnd: day(-1), endedAt: day(-1) }, "free", "free"],
    ["canceled immediately", { status: "canceled", endedAt: day(-1), canceledAt: day(-1) }, "free", "free"],
    ["unpaid", { status: "unpaid" }, "free", "free"],
    ["incomplete (first payment pending)", { status: "incomplete" }, "free", "free"],
    ["incomplete_expired", { status: "incomplete_expired" }, "free", "free"],
    ["paused", { status: "paused" }, "free", "free"],
    ["unknown status", { status: "something_new" }, "free", "free"],
  ]; // prettier-ignore
  it.each(cases)("%s", (_label, over, tier, state) => {
    const e = entitlementOf(sub(over), NOW);
    expect(e.tier).toBe(tier);
    expect(e.state).toBe(state);
  });

  it("canceling keeps Premium exactly until the end", () => {
    const s = sub({ cancelAtPeriodEnd: true, currentPeriodEnd: day(2) });
    expect(entitlementOf(s, day(2 - 1e-6)).tier).toBe("premium");
    expect(entitlementOf(s, day(2)).tier).toBe("free");
    expect(entitlementOf(s, NOW).premiumUntil).toEqual(day(2));
  });

  it("no subscriptions → Free", () => {
    expect(entitlementFrom([], NOW)).toMatchObject({
      tier: "free",
      state: "free",
      subscription: null,
    });
  });

  it("several subscriptions: the best Premium one wins, else the latest one is described", () => {
    const old = sub({ id: "sub_old", status: "canceled", endedAt: day(-40) });
    const cur = sub({ id: "sub_new", status: "active" });
    expect(entitlementFrom([old, cur], NOW).subscription?.id).toBe("sub_new");
    const a = sub({ id: "a", status: "canceled", endedAt: day(-40) });
    const b = sub({ id: "b", status: "incomplete_expired", endedAt: day(-2) });
    const e = entitlementFrom([a, b], NOW);
    expect(e.tier).toBe("free");
    expect(e.subscription?.id).toBe("b");
    const pd = sub({ id: "pd", status: "past_due" });
    const act = sub({ id: "act", status: "active" });
    expect(entitlementFrom([pd, act], NOW).state).toBe("active");
  });
});

describe("trial eligibility (one trial per account)", () => {
  it("only accounts that never had a trial", () => {
    expect(trialEligible(null, [])).toBe(true);
    expect(trialEligible(null, [{ trialEnd: null }])).toBe(true); // subscribed without a trial
    expect(trialEligible(day(-30), [])).toBe(false); // recorded trial
    expect(trialEligible(null, [{ trialEnd: day(-30) }])).toBe(false); // a past trialing subscription
  });
});

// ------------------------------------------------------------------ Checkout parameters

describe("Checkout Session parameters", () => {
  const base = {
    customerId: "cus_1",
    userId: "u1",
    priceId: "price_premium",
    siteUrl: "https://getedgefront.com",
    taxEnabled: false,
  };
  it("first time: 7-day trial, card always collected, our customer, our URLs", () => {
    const p = checkoutSessionParams({ ...base, withTrial: true });
    expect(p).toMatchObject({
      mode: "subscription",
      customer: "cus_1",
      client_reference_id: "u1",
      line_items: [{ price: "price_premium", quantity: 1 }],
      payment_method_collection: "always",
      success_url: "https://getedgefront.com/account?checkout=success",
      cancel_url: "https://getedgefront.com/pricing?checkout=cancelled",
      automatic_tax: { enabled: false },
      subscription_data: {
        trial_period_days: 7,
        metadata: { user_id: "u1" },
        trial_settings: { end_behavior: { missing_payment_method: "cancel" } },
      },
    });
    expect(p).not.toHaveProperty("customer_update");
    expect(p).not.toHaveProperty("customer_email"); // the existing customer is reused
  });
  it("trial already used: no trial at all", () => {
    const p = checkoutSessionParams({ ...base, withTrial: false });
    expect(p.subscription_data).toEqual({ metadata: { user_id: "u1" } });
  });
  it("EdgeFront sells by default: Managed Payments explicitly off (accounts may default it on)", () => {
    const p = checkoutSessionParams({ ...base, withTrial: true });
    expect(p.managed_payments).toEqual({ enabled: false });
    expect(p.automatic_tax).toEqual({ enabled: false });
  });
  it("Managed Payments only if the owner switches it on; Stripe then handles tax", () => {
    const p = checkoutSessionParams({ ...base, withTrial: true, managedPayments: true });
    expect(p.managed_payments).toEqual({ enabled: true });
    expect(p).not.toHaveProperty("automatic_tax");
    expect(p.subscription_data?.trial_period_days).toBe(7);
  });
  it("tax switched on by config only", () => {
    const p = checkoutSessionParams({ ...base, withTrial: false, taxEnabled: true });
    expect(p.automatic_tax).toEqual({ enabled: true });
    expect(p.customer_update).toEqual({ address: "auto" });
  });
});

describe("config and safety", () => {
  it("the API version is pinned", () => expect(STRIPE_API_VERSION).toBe("2026-11-18.endive"));
  it("billing is off without a key and a price", () => {
    expect(billingConfig({})).toBeNull();
    expect(billingConfig({ STRIPE_SECRET_KEY: "sk_test_x" })).toBeNull();
  });
  it("restricted live keys are refused too", () => {
    expect(() => billingConfig({ STRIPE_SECRET_KEY: "rk_live_x", STRIPE_PRICE_ID: "price_1" })).toThrow();
    expect(billingConfig({ STRIPE_SECRET_KEY: "rk_test_x", STRIPE_PRICE_ID: "price_1" })).not.toBeNull();
  });
  it("test keys work; live keys are refused until Phase 11", () => {
    expect(billingConfig({ STRIPE_SECRET_KEY: "sk_test_x", STRIPE_PRICE_ID: "price_1" })?.taxEnabled).toBe(false);
    expect(() => billingConfig({ STRIPE_SECRET_KEY: "sk_live_x", STRIPE_PRICE_ID: "price_1" })).toThrow();
    expect(billingConfig({ STRIPE_SECRET_KEY: "sk_live_x", STRIPE_PRICE_ID: "p", STRIPE_ALLOW_LIVE: "true" })).not.toBeNull();
  });
  it("tax collection is a config flag", () => {
    expect(billingConfig({ STRIPE_SECRET_KEY: "sk_test_x", STRIPE_PRICE_ID: "p", STRIPE_TAX_ENABLED: "true" })?.taxEnabled).toBe(true);
    // Managed Payments (Stripe/Link as merchant of record) is on unless explicitly turned off
    expect(billingConfig({ STRIPE_SECRET_KEY: "sk_test_x", STRIPE_PRICE_ID: "p" })?.managedPayments).toBe(true);
    expect(billingConfig({ STRIPE_SECRET_KEY: "sk_test_x", STRIPE_PRICE_ID: "p", STRIPE_MANAGED_PAYMENTS: "false" })?.managedPayments).toBe(false);
  });
  it("the fake Stripe is local-only", () => {
    expect(e2eFakeStripeUrl({})).toBeNull();
    expect(e2eFakeStripeUrl({ E2E_FAKE_STRIPE_URL: "http://localhost:4466" })?.port).toBe("4466");
    expect(() => e2eFakeStripeUrl({ E2E_FAKE_STRIPE_URL: "https://stripe.example.com" })).toThrow();
    expect(() => e2eFakeStripeUrl({ E2E_FAKE_STRIPE_URL: "http://localhost:4466", RAILWAY_ENVIRONMENT_NAME: "production" })).toThrow();
  });
}); // prettier-ignore

describe("format", () => {
  it("money and days", () => {
    expect(formatMoney(2000, "usd")).toBe("$20.00");
    expect(formatMoney(2000, "usd", true)).toBe("$20");
    expect(formatMoney(1999, "usd", true)).toBe("$19.99");
    expect(formatDay("2026-12-03T05:00:00Z", "UTC")).toBe("Dec 3, 2026");
  });
});

// ------------------------------------------------------------------ Stripe objects

const unix = (d: Date) => Math.floor(d.getTime() / 1000);

function stripeSub(over: Record<string, unknown> = {}): Stripe.Subscription {
  return {
    id: "sub_1",
    object: "subscription",
    customer: "cus_1",
    status: "trialing",
    cancel_at_period_end: false,
    cancel_at: null,
    canceled_at: null,
    ended_at: null,
    trial_end: unix(day(7)),
    metadata: { user_id: "u1" },
    latest_invoice: { id: "in_1", object: "invoice", status: "paid" },
    items: {
      object: "list",
      data: [
        {
          id: "si_1",
          price: { id: "price_1", unit_amount: 2000, currency: "usd" },
          current_period_end: unix(day(7)),
        },
      ],
    },
    ...over,
  } as unknown as Stripe.Subscription;
}

function event(type: string, object: Record<string, unknown>, id = `evt_${Math.random().toString(36).slice(2)}`): Stripe.Event {
  return { id, object: "event", type, created: unix(NOW), data: { object } } as unknown as Stripe.Event;
} // prettier-ignore

describe("mapping Stripe → mirror", () => {
  it("period end comes from the subscription items (API 2026-11-18.endive)", () => {
    const s = snapshotFromStripe(stripeSub());
    expect(s).toMatchObject({
      id: "sub_1",
      customerId: "cus_1",
      userIdFromMetadata: "u1",
      status: "trialing",
      priceId: "price_1",
      currentPeriodEnd: new Date(unix(day(7)) * 1000),
      trialEnd: new Date(unix(day(7)) * 1000),
      cancelAtPeriodEnd: false,
      latestInvoiceStatus: "paid",
    });
    expect(snapshotFromStripe(stripeSub({ latest_invoice: "in_1" })).latestInvoiceStatus).toBeNull();
  });
  it("finds the subscription of every handled event type", () => {
    expect(subscriptionIdOf(event("checkout.session.completed", { mode: "subscription", subscription: "sub_9" }))).toBe("sub_9");
    expect(subscriptionIdOf(event("checkout.session.completed", { mode: "payment", subscription: null }))).toBeNull();
    for (const t of ["customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted", "customer.subscription.trial_will_end"])
      expect(subscriptionIdOf(event(t, { id: "sub_2" }))).toBe("sub_2");
    expect(subscriptionIdOf(event("invoice.paid", { parent: { subscription_details: { subscription: "sub_3" } } }))).toBe("sub_3");
    expect(subscriptionIdOf(event("invoice.payment_failed", { subscription: "sub_4" }))).toBe("sub_4");
    expect(subscriptionIdOf(event("charge.refunded", { id: "ch_1" }))).toBeNull();
    expect(WEBHOOK_EVENTS).toHaveLength(7);
  });
}); // prettier-ignore

// ------------------------------------------------------------------ webhook handling

function memoryStore() {
  const customers = new Map<string, { stripeCustomerId: string; trialUsedAt: Date | null }>();
  const subs = new Map<
    string,
    { userId: string; snap: SubscriptionSnapshot; eventId: string | null }
  >();
  const events = new Map<string, { processed: boolean; error: string | null }>();
  const deletedUsers = new Set<string>();
  const store: BillingStore = {
    async customerOf(u) { return customers.get(u) ?? null; },
    async userOfCustomer(c) { for (const [u, v] of customers) if (v.stripeCustomerId === c) return u; return null; },
    async saveCustomer(u, c) {
      if (deletedUsers.has(u)) throw new Error("foreign key");
      if (!customers.has(u)) customers.set(u, { stripeCustomerId: c, trialUsedAt: null });
      return customers.get(u)!.stripeCustomerId;
    },
    async subscriptionsOf(u) { return [...subs.values()].filter((s) => s.userId === u).map((s) => s.snap); },
    async saveSubscription(u, _c, s, e) { subs.set(s.id, { userId: u, snap: s, eventId: e }); },
    async markTrialUsed(u, at) { const c = customers.get(u); if (c && !c.trialUsedAt) c.trialUsedAt = at; },
    async beginEvent(id) { const e = events.get(id); if (e?.processed) return "processed"; if (!e) events.set(id, { processed: false, error: null }); return "new"; },
    async finishEvent(id, error) { events.set(id, error ? { processed: false, error } : { processed: true, error: null }); },
  }; // prettier-ignore
  return { store, customers, subs, events, deletedUsers };
}

describe("webhook handling", () => {
  it("verifies the signature over the raw body; tampering or a wrong secret fails", () => {
    const stripe = new Stripe("sk_test_dummy");
    const secret = "whsec_test_secret";
    const payload = JSON.stringify({
      id: "evt_sig",
      object: "event",
      type: "invoice.paid",
      data: { object: {} },
    });
    const header = stripe.webhooks.generateTestHeaderString({ payload, secret });
    expect(stripe.webhooks.constructEvent(payload, header, secret).id).toBe("evt_sig");
    expect(() =>
      stripe.webhooks.constructEvent(payload.replace("evt_sig", "evt_xxx"), header, secret),
    ).toThrow();
    expect(() => stripe.webhooks.constructEvent(payload, header, "whsec_other")).toThrow();
    expect(() => stripe.webhooks.constructEvent(payload, "t=1,v1=deadbeef", secret)).toThrow();
  });

  it("mirrors the current subscription and records the trial; duplicates are ignored", async () => {
    const m = memoryStore();
    m.customers.set("u1", { stripeCustomerId: "cus_1", trialUsedAt: null });
    let fetches = 0;
    const deps = { store: m.store, fetchSubscription: async () => (fetches++, stripeSub()) };
    const e = event(
      "checkout.session.completed",
      { mode: "subscription", subscription: "sub_1" },
      "evt_a",
    );
    expect(await handleEvent(e, deps)).toEqual({
      result: "mirrored",
      userId: "u1",
      status: "trialing",
    });
    expect(m.customers.get("u1")!.trialUsedAt).toEqual(NOW);
    expect(m.subs.get("sub_1")!.eventId).toBe("evt_a");
    expect(await handleEvent(e, deps)).toEqual({ result: "duplicate" });
    expect(fetches).toBe(1);
  });

  it("out of order: a late 'created' event can't undo a newer state", async () => {
    const m = memoryStore();
    m.customers.set("u1", { stripeCustomerId: "cus_1", trialUsedAt: null });
    let current = stripeSub({ status: "active", trial_end: null, cancel_at_period_end: true });
    const deps = { store: m.store, fetchSubscription: async () => current };
    await handleEvent(
      event("customer.subscription.updated", { id: "sub_1", status: "active" }),
      deps,
    );
    // the older "created" (trialing) arrives afterwards: we still mirror what Stripe says *now*
    await handleEvent(
      event("customer.subscription.created", { id: "sub_1", status: "trialing" }),
      deps,
    );
    expect(m.subs.get("sub_1")!.snap).toMatchObject({ status: "active", cancelAtPeriodEnd: true });
    current = stripeSub({ status: "canceled", ended_at: unix(NOW), trial_end: null });
    await handleEvent(event("customer.subscription.deleted", { id: "sub_1" }), deps);
    expect(m.subs.get("sub_1")!.snap.status).toBe("canceled");
  });

  it("every status transition updates the mirror and the entitlement", async () => {
    const m = memoryStore();
    m.customers.set("u1", { stripeCustomerId: "cus_1", trialUsedAt: null });
    let current = stripeSub();
    const deps = { store: m.store, fetchSubscription: async () => current };
    const steps: [string, Record<string, unknown>, string, "premium" | "free"][] = [
      ["customer.subscription.created", {}, "trialing", "premium"],
      ["invoice.paid", { status: "active", trial_end: unix(day(-1)) }, "active", "premium"],
      ["invoice.payment_failed", { status: "past_due", latest_invoice: { status: "open" } }, "past_due", "premium"],
      ["invoice.paid", { status: "active" }, "active", "premium"],
      ["customer.subscription.updated", { status: "active", cancel_at_period_end: true }, "canceling", "premium"],
      ["customer.subscription.updated", { status: "active", cancel_at_period_end: false }, "active", "premium"],
      ["customer.subscription.updated", { status: "unpaid" }, "free", "free"],
      ["customer.subscription.deleted", { status: "canceled", ended_at: unix(NOW) }, "free", "free"],
    ]; // prettier-ignore
    for (const [type, over, state, tier] of steps) {
      current = stripeSub({ ...over });
      const obj = type.startsWith("invoice")
        ? { parent: { subscription_details: { subscription: "sub_1" } } }
        : { id: "sub_1" };
      const out = await handleEvent(event(type, obj), deps);
      expect(out.result).toBe("mirrored");
      const e = entitlementFrom(await m.store.subscriptionsOf("u1"), NOW);
      expect([type, e.state, e.tier]).toEqual([type, state, tier]);
    }
  });

  it("a deleted account: nothing is mirrored and nothing breaks", async () => {
    const m = memoryStore();
    m.deletedUsers.add("u1");
    const out = await handleEvent(event("customer.subscription.deleted", { id: "sub_1" }), {
      store: m.store,
      fetchSubscription: async () => stripeSub({ status: "canceled" }),
    });
    expect(out).toEqual({ result: "no_user" });
    expect(m.subs.size).toBe(0);
  });

  it("unknown customer but our user id in metadata: links the customer", async () => {
    const m = memoryStore();
    const out = await handleEvent(event("customer.subscription.created", { id: "sub_1" }), {
      store: m.store,
      fetchSubscription: async () => stripeSub({ customer: "cus_new" }),
    });
    expect(out).toMatchObject({ result: "mirrored", userId: "u1" });
    expect(m.customers.get("u1")!.stripeCustomerId).toBe("cus_new");
  });

  it("a failure leaves the event unprocessed so Stripe's retry handles it", async () => {
    const m = memoryStore();
    m.customers.set("u1", { stripeCustomerId: "cus_1", trialUsedAt: null });
    let fail = true;
    const deps = {
      store: m.store,
      fetchSubscription: async () => {
        if (fail) throw new Error("stripe unavailable");
        return stripeSub({ status: "active" });
      },
    };
    const e = event(
      "invoice.paid",
      { parent: { subscription_details: { subscription: "sub_1" } } },
      "evt_retry",
    );
    expect(await handleEvent(e, deps)).toEqual({ result: "error", message: "stripe unavailable" });
    expect(m.events.get("evt_retry")).toEqual({ processed: false, error: "stripe unavailable" });
    fail = false;
    expect(await handleEvent(e, deps)).toMatchObject({ result: "mirrored", status: "active" });
  });

  it("ignores events we don't act on, once", async () => {
    const m = memoryStore();
    const deps = { store: m.store, fetchSubscription: async () => stripeSub() };
    const e = event("charge.refunded", { id: "ch_1" }, "evt_other");
    expect(await handleEvent(e, deps)).toEqual({ result: "ignored" });
    expect(await handleEvent(e, deps)).toEqual({ result: "duplicate" });
  });

  it("trial_will_end triggers our reminder only while trialing", async () => {
    const m = memoryStore();
    m.customers.set("u1", { stripeCustomerId: "cus_1", trialUsedAt: null });
    const sent: string[] = [];
    const deps = {
      store: m.store,
      fetchSubscription: async () => stripeSub(),
      onTrialWillEnd: async (u: string) => void sent.push(u),
    };
    await handleEvent(event("customer.subscription.trial_will_end", { id: "sub_1" }), deps);
    expect(sent).toEqual(["u1"]);
    await handleEvent(event("customer.subscription.trial_will_end", { id: "sub_1" }), {
      ...deps,
      fetchSubscription: async () => stripeSub({ status: "canceled" }),
    });
    expect(sent).toEqual(["u1"]);
  });
});

describe("test-mode allowlist (BILLING_TEST_ALLOWLIST)", () => {
  const test = { STRIPE_SECRET_KEY: "sk_test_x" };
  it("parses addresses and domains, separated by commas or spaces", () => {
    expect(parseAllowlist(" Owner@Example.com, @team.example.org  qa@x.io ")).toEqual(["owner@example.com", "@team.example.org", "qa@x.io"]);
    expect(parseAllowlist(undefined)).toEqual([]);
  });
  it("test mode: only listed emails or domains", () => {
    const env = { ...test, BILLING_TEST_ALLOWLIST: "owner@example.com, @team.example.org" };
    expect(checkoutAllowed("OWNER@example.com", env)).toBe(true);
    expect(checkoutAllowed("anyone@team.example.org", env)).toBe(true);
    expect(checkoutAllowed("someone@example.com", env)).toBe(false);
    expect(checkoutAllowed("x@sub.team.example.org", env)).toBe(false); // exact domain only
    expect(checkoutAllowed("owner@example.com.evil.io", env)).toBe(false);
  });
  it("test mode with no list: nobody", () => {
    expect(checkoutAllowed("owner@example.com", test)).toBe(false);
    expect(testModeGate(test)).toBe(true);
  });
  it("live mode (Phase 11): the list no longer applies", () => {
    expect(checkoutAllowed("anyone@example.com", { STRIPE_SECRET_KEY: "sk_live_x" })).toBe(true);
    expect(testModeGate({ STRIPE_SECRET_KEY: "rk_live_x" })).toBe(false);
  });
}); // prettier-ignore
