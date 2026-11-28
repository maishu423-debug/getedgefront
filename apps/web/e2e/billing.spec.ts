import { expect, type APIRequestContext, type Page, test } from "@playwright/test";

import { formAlert, mails, signIn, signUp, uniqueEmail, verify } from "./auth-helpers";

// Billing (v2 Phase 8) against the local fake Stripe (e2e/fake-stripe.mjs): never real Stripe.
// Needs the web server started with E2E_FAKE_STRIPE_URL, STRIPE_* test values and the email
// outbox (see infra/stripe-setup.md, "Running the billing tests").
const FAKE_STRIPE = process.env.E2E_FAKE_STRIPE_URL ?? "http://localhost:4466";
const isPhone = (page: Page) => (page.viewportSize()?.width ?? 1440) < 640;

type FakeState = {
  customers: { id: string; email: string }[];
  subscriptions: { id: string; status: string; cancel_at_period_end: boolean }[];
  sessions: { trial_days: number | null; payment_method_collection: string; customer: string }[];
};

async function fake(request: APIRequestContext, email: string): Promise<FakeState> {
  const res = await request.get(`${FAKE_STRIPE}/__by-email?email=${encodeURIComponent(email)}`);
  return (await res.json()) as FakeState;
}

/** Reloads /account until the subscription card shows `state` (webhooks arrive after a delay). */
async function expectBillingState(page: Page, state: string) {
  await expect
    .poll(
      async () => {
        await page.goto("/account");
        return page.locator("[data-billing-state]").getAttribute("data-billing-state");
      },
      { timeout: 20_000, intervals: [500, 1000, 2000] },
    )
    .toBe(state);
}

/** Signed-up, verified, signed-in user who has just started the 7-day trial. */
async function startTrial(page: Page, email: string) {
  await signUp(page, "Paying Customer", email);
  await verify(page, email);
  await page.goto("/pricing");
  await page.getByRole("button", { name: "Start 7-day free trial" }).click();
  await expect(page).toHaveURL(/localhost:4466\/checkout\//);
  await expect(page.getByTestId("offer")).toContainText("7-day free trial");
  await page.getByRole("button", { name: "Start trial" }).click();
  await expect(page).toHaveURL(/\/account\?checkout=success/);
}

test.describe("billing", () => {
  test.skip(!process.env.E2E_EMAIL_OUTBOX, "billing e2e needs E2E_EMAIL_OUTBOX");

  test("trial: checkout → webhook → Premium everywhere", async ({ page, request }, info) => {
    const email = uniqueEmail(info, "trial");
    await startTrial(page, email);
    // the return from Checkout grants nothing by itself: it waits for the webhook
    await expect(page.getByText("Activating Premium")).toBeVisible();
    await expect(page.locator("[data-billing-state]")).toHaveAttribute("data-billing-state", "trialing", { timeout: 20_000 });
    await expect(page).toHaveURL(/\/account$/);
    const card = page.locator("[data-billing-state]");
    await expect(card.getByText("FREE TRIAL", { exact: true })).toBeVisible();
    await expect(card).toContainText("Premium · free trial");
    await expect(card).toContainText(/Trial ends \w{3} \d+, \d{4}\. You'll be charged \$20 \+ tax on \w{3} \d+, \d{4} unless you cancel\./);
    await expect(card).toContainText("(Card ending 4242.)");
    await expect(card).toContainText("Premium · $20 / month");
    await expect(card).toContainText("Visa •••• 4242");
    if (!isPhone(page)) {
      await expect(page.getByTestId("plan-badge")).toHaveText("PREMIUM");
      const nav = page.getByRole("navigation", { name: "Main" }); // the visible (desktop) nav
      await expect(nav.getByTestId("pro-pill")).toHaveClass(/invisible/);
    }
    // Checkout was created server-side with the trial, the card always collected, one customer
    const s = await fake(request, email);
    expect(s.customers).toHaveLength(1);
    expect(s.sessions[0]).toMatchObject({ trial_days: 7, payment_method_collection: "always", customer: s.customers[0]!.id });
    await page.goto("/pricing");
    await expect(page.getByText("You're on Premium")).toBeVisible();
    await expect(page.getByRole("button", { name: "Manage billing" })).toBeVisible();
  }); // prettier-ignore

  test("cancel in the portal → canceled state, then resume", async ({ page }, info) => {
    const email = uniqueEmail(info, "cancel");
    await startTrial(page, email);
    await expectBillingState(page, "trialing");
    await page.getByRole("button", { name: "Manage billing" }).click();
    await expect(page).toHaveURL(/localhost:4466\/portal\//);
    await page.getByRole("button", { name: "Cancel plan" }).click();
    await expect(page).toHaveURL(/\/account$/);
    await expectBillingState(page, "canceling");
    const card = page.locator("[data-billing-state]");
    await expect(card.getByText("CANCELLED", { exact: true })).toBeVisible();
    await expect(card).toContainText("Premium until");
    await expect(card).toContainText("until your trial ends");
    // EdgeFront's own confirmation (Refund & Cancellation Policy), exactly once
    await expect.poll(() => mails(email, "subscription_cancelled").length).toBe(1);
    expect(mails(email, "subscription_cancelled")[0]!.text).toMatch(
      /Your Premium subscription is cancelled\. You keep Premium until \w{3} \d+, \d{4}\. You won't be charged again\./,
    );
    await page.getByRole("button", { name: "Resume or manage" }).click();
    await page.getByRole("button", { name: "Renew plan" }).click();
    await expectBillingState(page, "trialing");
  });

  test("payment failure → past_due banner; recovery → active", async ({ page, request }, info) => {
    const email = uniqueEmail(info, "pastdue");
    await startTrial(page, email);
    await expectBillingState(page, "trialing");
    const sub = (await fake(request, email)).subscriptions[0]!;
    await request.post(`${FAKE_STRIPE}/__subscriptions/${sub.id}/fail_payment`);
    await expectBillingState(page, "past_due");
    const card = page.locator("[data-billing-state]");
    await expect(card.getByText("PAYMENT FAILED", { exact: true })).toBeVisible();
    await expect(card).toContainText("Amount due");
    await expect(card).toContainText("$20.00");
    await expect(
      formAlert(page).filter({ hasText: "Update your card to keep Premium" }),
    ).toBeVisible();
    await page.goto("/");
    await expect(
      page
        .getByRole("alert")
        .filter({ hasText: "Payment failed. Update your card to keep Premium." }),
    ).toBeVisible();
    await request.post(`${FAKE_STRIPE}/__subscriptions/${sub.id}/recover`);
    await expectBillingState(page, "active");
    await expect(page.locator("[data-billing-state]")).toContainText("Renews on");
  });

  test("trial used → Subscribe, with no second trial", async ({ page, request }, info) => {
    const email = uniqueEmail(info, "used");
    await startTrial(page, email);
    await expectBillingState(page, "trialing");
    const sub = (await fake(request, email)).subscriptions[0]!;
    await request.post(`${FAKE_STRIPE}/__subscriptions/${sub.id}/end`);
    await expectBillingState(page, "free");
    const card = page.locator("[data-billing-state]");
    await expect(card).toContainText("Already used");
    await card.getByRole("button", { name: "Subscribe" }).click();
    await expect(page).toHaveURL(/localhost:4466\/checkout\//);
    await expect(page.getByTestId("offer")).toContainText("No trial");
    const s = await fake(request, email);
    expect(s.customers).toHaveLength(1); // the same Stripe customer is reused
    expect(s.sessions.at(-1)!.trial_days).toBeNull();
  });

  test("deleting the account cancels the subscription first", async ({ page, request }, info) => {
    const email = uniqueEmail(info, "delsub");
    await startTrial(page, email);
    await expectBillingState(page, "trialing");
    await page.getByRole("button", { name: "Delete account" }).click();
    await page.getByRole("button", { name: "Delete my account permanently" }).click();
    await expect(page).toHaveURL(/\/\?account=deleted/);
    const s = await fake(request, email);
    expect(s.subscriptions[0]!.status).toBe("canceled");
    expect(s.customers).toHaveLength(1); // the Stripe customer is kept (invoices)
  });

  test("an unverified email must be confirmed before the trial", async ({ page }, info) => {
    const email = uniqueEmail(info, "unverified");
    await signUp(page, "Not Yet", email);
    await signIn(page, email);
    await expect(page).toHaveURL(/\/$/); // signed in (unverified emails may sign in and browse)
    await page.goto("/pricing");
    await expect(page.getByText("Confirm your email address to start the trial")).toBeVisible();
    await expect(page.getByRole("button", { name: "Start 7-day free trial" })).toHaveCount(0);
    await page.getByRole("button", { name: "Resend the link" }).click();
    await expect(page.getByText("Sent. Check your inbox.")).toBeVisible();
  });

  test("the price shown comes from Stripe", async ({ page }) => {
    await page.goto("/pricing");
    await expect(page.getByTestId("premium-price")).toHaveText(/\$20\s*per month/);
    await expect(page.getByText(/Free for 7 days/)).toHaveCount(0); // the full terms only, once
    await expect(page.getByText(/Sales tax is added at checkout where it applies/)).toBeVisible();
    await expect(
      page.getByText(/Sold through Link \(Stripe\), the seller of record/),
    ).toBeVisible();
  });

  test("test mode: only allow-listed emails may subscribe", async ({ page }) => {
    // the test web server allow-lists @example.org only (BILLING_TEST_ALLOWLIST)
    const email = `outsider-${Date.now()}-${Math.random().toString(36).slice(2, 6)}@example.net`;
    await page.goto("/pricing");
    await expect(page.getByText("Premium is coming soon")).toBeVisible(); // signed out
    await signUp(page, "Outsider", email);
    await verify(page, email);
    await page.goto("/pricing");
    await expect(page.getByText("Premium is coming soon")).toBeVisible();
    await expect(page.getByRole("button", { name: "Start 7-day free trial" })).toHaveCount(0);
    const res = await page.request.post("/api/billing/checkout", {
      data: { clickId: "abcdefgh12" },
      headers: { origin: "http://localhost:3000" },
    });
    expect(res.status()).toBe(403);
    expect(await res.json()).toEqual({ code: "not_available" });
    await page.goto("/account");
    await expect(page.locator("[data-billing-state]")).toContainText("Premium is coming soon");
  });

  test("billing endpoints refuse bad requests", async ({ request }) => {
    const hook = "/api/stripe/webhook";
    expect((await request.post(hook, { data: "{}" })).status()).toBe(400); // unsigned
    const forged = await request.post(hook, {
      data: JSON.stringify({ id: "evt_forged", type: "customer.subscription.updated" }),
      headers: { "stripe-signature": `t=${Math.floor(Date.now() / 1000)},v1=${"0".repeat(64)}`, "content-type": "application/json" },
    });
    expect(forged.status()).toBe(400);
    const origin = { "content-type": "application/json" };
    expect((await request.post("/api/billing/checkout", { data: { clickId: "abcdefgh12" }, headers: { ...origin, origin: "https://evil.example.com" } })).status()).toBe(403);
    expect((await request.post("/api/billing/checkout", { data: { clickId: "abcdefgh12" }, headers: { ...origin, origin: "http://localhost:3000" } })).status()).toBe(401);
    expect((await request.post("/api/billing/portal", { data: {}, headers: { ...origin, origin: "http://localhost:3000" } })).status()).toBe(401);
    expect(await (await request.get("/api/me")).json()).toEqual({ signedIn: false, tier: "anonymous" });
  }); // prettier-ignore
});
