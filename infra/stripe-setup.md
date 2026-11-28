# Billing: Stripe setup (v2 Phase 8) — TEST MODE ONLY

What you (the owner) set up so Premium subscriptions work. Everything here is **test mode**
until Phase 11: production also runs with test keys, so nobody can pay real money yet. The
server refuses `sk_live_` keys unless `STRIPE_ALLOW_LIVE=true` (set only in Phase 11).

**While in test mode only emails in `BILLING_TEST_ALLOWLIST` can start Checkout;** everyone else
sees "Premium is coming soon". The list stops applying with a live key.

Pinned Stripe API version: **`2026-11-18.endive`** (stripe-node 23.2.0). Free trial: Checkout
`subscription_data.trial_period_days = 7` (Stripe's stable mechanism; "trial offers" are a private
preview in Checkout), card always collected, one trial per account.

---

## Your Dashboard steps, in order

Make sure the Dashboard shows **Test mode** (toggle at the top) for every step.

1. **Business details** — Settings → Business → Public details
   (<https://dashboard.stripe.com/settings/public>): public business name "EdgeFront", website
   `https://getedgefront.com`, support email (an address you read), support URL
   `https://getedgefront.com`. **Statement descriptor:** `EDGEFRONT` (max 22 characters; shown on
   card statements).
2. **Trial reminder email (card-network rule for trials)** — Settings → Billing → Subscriptions
   and emails (<https://dashboard.stripe.com/settings/billing/automatic>) → *Manage free trial
   messaging*: turn on **"Send a reminder email 7 days before a free trial ends"** and choose
   *Link to a Stripe-hosted page*. Our trial is 7 days, so Stripe sends it when the trial starts.
   Stripe does **not** send these emails in test mode.
   - Same page, **"Trial ending events"**: the number of days before the trial ends that Stripe
     sends `customer.subscription.trial_will_end`. EdgeFront sends its own reminder email then,
     and the pricing page says "we'll email you **3** days before". Keep **3**, or tell me if you
     set 2 (the design's wording) and I'll change the copy to match.
3. **Failed payments (dunning)** — Billing → Revenue recovery → Retries
   (<https://dashboard.stripe.com/revenue_recovery/retries>): keep **Smart Retries** (Stripe's
   default: up to 8 retries within 2 weeks). *If all retries for a payment fail*: **Cancel the
   subscription** (the account then moves to Free). While Stripe retries, the account stays
   Premium with a "payment failed" notice.
   Emails (<https://dashboard.stripe.com/revenue_recovery/emails>): turn on **"Send emails when
   card payments fail"** and **"Send emails about expiring cards"**.
4. **Stripe Tax: leave it off.** With Managed Payments, Stripe (Link) is the merchant of record and
   calculates, collects and remits sales tax itself; EdgeFront doesn't register or file anywhere.
   (Stripe Tax would only matter in countries Managed Payments doesn't cover for tax; Japan
   domestic sales and Singapore B2B are the listed exceptions, irrelevant for US customers.)
5. **Managed Payments (owner decision 2026-11-27: ON) and payment methods**
   - **What it means.** Stripe sells EdgeFront Premium *through Link* as the merchant of record.
     Verified in test mode:
     - Checkout is Link-branded and says "By subscribing, you agree to Link's Terms and Privacy
       Policy and authorize Link to charge you … This subscription is provided by EdgeFront in
       accordance with their terms. **Sold through Link**".
     - **Tax is added on top of $20**, by billing address: Checkout shows "Subtotal $20.00 · Tax
       (calculated from the address) · Total after trial". Test addresses gave $0.00 tax in New
       York and $21.60–$22.11 totals in other states. Our price is tax-*exclusive*; this can't be
       changed on an existing price (a new tax-inclusive price would make $20 the total).
     - Card statements read `LINK.COM* EDGEFRONT`. Receipts and invoices come from Link ("Sold
       through Link, LLC"), not from your Stripe receipt settings.
     - The subscription webhooks, our account page (Stripe's own invoice preview gives the exact
       next charge, tax included), the Customer Portal and API cancellation (account deletion) all
       work unchanged.
   - **Refunds, disputes, support** (Stripe's Managed Payments docs, "How it works"):
     - Customers reach payment and subscription support through **Link support**, and can manage
       their subscription, card and billing address on the **Link website**. You still handle
       product questions, and can refund or update subscriptions yourself.
     - Stripe can refund within 60 days "in certain cases" and may refund without your approval
       if you don't answer a support escalation within **48 hours**. Refunds include the sales
       tax.
     - **Stripe handles disputes** (it may accept rather than fight one). A dispute fee applies
       (see stripe.com/pricing). Managed Payments' own fee is on that page too; I couldn't read it.
     - Keep the **support email** current (Settings → Business details): Stripe uses it for every
       escalation.
   - **Payment methods: Cards, Apple Pay, Google Pay and Link only (owner decision).** Managed
     Payments chooses methods dynamically from Stripe-managed payment method configurations; the
     API can't take a list. Your account has three, named **"Managed Payments Configuration 1",
     "2" and "3"**. In **Settings → Payment methods**, open each of them (configuration picker at
     the top) and turn **off** everything except **Cards, Apple Pay, Google Pay, Link**:
     - **Cash App Pay** (it appeared in our US Checkout)
     - **Klarna** and **Afterpay / Clearpay** (off by default for Managed Payments, but listed in
       configuration 3)
     - **Bancontact**, **Crypto**
     - **Kakao Pay, Korean cards, Naver Pay, PAYCO, Samsung Pay**
     **Not the "Default" configuration:** switches there don't affect Managed Payments Checkout
     (verified 2026-11-27: a Managed Payments session still offered `card` + `cashapp` after
     Cash App Pay was turned off in "Default").
     Stripe notes that Managed Payments "controls the payment methods available" (support article
     "Payment method configurations for Managed Payments"). If a switch can't be turned off, it's
     a Managed Payments limit: tell me which one. After switching, open a test Checkout: it
     should show only Card (plus Apple Pay / Google Pay / Link where the browser supports them).
   - **Before live mode (Phase 11)**:
     1. Activate Managed Payments in live mode (Settings → Managed Payments). Stripe runs an
        **eligibility review**: digital products only, sold directly by you, from an eligible
        country (US is).
     2. Every product needs an **eligible tax code**. The setup script sets
        `txcd_10000000` ("General – electronically supplied services"); ask your accountant
        whether a SaaS code (`txcd_10103000` personal / `txcd_10103001` business use) fits better,
        then re-run it with `--tax-code …`.
     3. Keep the support email current, and answer Stripe's escalations within 48 h.
     4. Checkout can't use a custom domain with Managed Payments.
     5. Have your Terms and Privacy Policy reviewed (see `docs/privacy-data-inventory.md`, notes
        for the lawyer).
6. **API key** — Developers → API keys: copy the **test** secret key (`sk_test_…`). Better: create
   a *restricted* test key with write access to Products, Prices, Customers, Checkout Sessions,
   Subscriptions, Customer portal, Webhook endpoints and Test clocks.
7. **Products, price, portal, webhook** — run the setup script (or let me run it with your test
   key in the repo's `.env`):

   ```sh
   cd apps/web
   STRIPE_SECRET_KEY=sk_test_... node scripts/stripe-setup.mjs \
     --site https://getedgefront.com \
     --webhook-url https://getedgefront.com/api/stripe/webhook
   ```

   It creates or verifies, and is safe to run again:
   - Product **EdgeFront Premium** with an eligible tax code (default `txcd_10000000`,
     `--tax-code` to change) and a monthly price of **$20.00 USD** (lookup key
     `edgefront_premium_monthly_usd`, tax exclusive: tax is added on top).
   - **Customer Portal** configuration: update payment method, invoice history, cancel at period
     end (no cancellation-reason question), **no** plan switching or quantity changes, no email editing; returns to
     `/account`.
   - **Webhook endpoint** on the URL above with exactly these events:
     `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`,
     `customer.subscription.deleted`, `customer.subscription.trial_will_end`, `invoice.paid`,
     `invoice.payment_failed` (API version pinned to `2026-11-18.endive`).

   It prints `STRIPE_PRICE_ID`, `STRIPE_PORTAL_CONFIGURATION_ID` and, the first time only,
   `STRIPE_WEBHOOK_SECRET` (Stripe shows it once; lost → Developers → Webhooks → Roll secret).
8. **Railway → web → Variables**, then Deploy:

   | Variable | Value | |
   |---|---|---|
   | `STRIPE_SECRET_KEY` | your `sk_test_…` / `rk_test_…` key | 🔒 |
   | `STRIPE_WEBHOOK_SECRET` | `whsec_…` from step 7 | 🔒 |
   | `STRIPE_PRICE_ID` | `price_…` from step 7 | |
   | `STRIPE_PORTAL_CONFIGURATION_ID` | `bpc_…` from step 7 | |
   | `STRIPE_MANAGED_PAYMENTS` | `true` (step 5; also the default) | |
   | `BILLING_TEST_ALLOWLIST` | the emails allowed to subscribe while in test mode, e.g. `you@yourdomain.com` (comma-separated; `@domain` allows a whole domain; empty = nobody) | |

   Never set `STRIPE_ALLOW_LIVE` or `E2E_FAKE_STRIPE_URL` on Railway (the server refuses the fake
   on Railway).

**Changing the price later:** create a new price on the product in Stripe and set
`STRIPE_PRICE_ID` to it (existing subscribers keep their old price until you migrate them). The
site reads the amount from Stripe and refreshes it within 10 minutes; no code change.

## What we store

Only Stripe ids, statuses and dates (`billing.customers`, `billing.subscriptions`,
`billing.webhook_events`). Card details stay at Stripe; the account page reads the card brand and
last 4 digits live from Stripe to display them and doesn't store them. See
`docs/privacy-data-inventory.md`.

## Local development and tests

- **Automated tests (and CI)** never contact Stripe: they use `e2e/fake-stripe.mjs`, started by
  Playwright, with the web server run with
  `E2E_FAKE_STRIPE_URL=http://localhost:4466 STRIPE_SECRET_KEY=sk_test_fake STRIPE_PRICE_ID=price_e2e_premium STRIPE_WEBHOOK_SECRET=whsec_e2e_secret`
  (see `infra/auth-setup.md` §5 for the rest of the test environment).
- **Real Stripe test mode on your machine:** put the test key in `apps/web/.env.local`
  (`STRIPE_SECRET_KEY`, `STRIPE_PRICE_ID`, `STRIPE_PORTAL_CONFIGURATION_ID`), then forward webhooks
  with the Stripe CLI (<https://docs.stripe.com/stripe-cli>):

  ```sh
  stripe listen --api-key sk_test_... \
    --events checkout.session.completed,customer.subscription.created,customer.subscription.updated,customer.subscription.deleted,customer.subscription.trial_will_end,invoice.paid,invoice.payment_failed \
    --forward-to http://localhost:3000/api/stripe/webhook
  ```

  It prints `whsec_…`: set it as `STRIPE_WEBHOOK_SECRET` and restart the web server. Test cards:
  `4242 4242 4242 4242` (works), `4000 0000 0000 0002` (declined), `4000 0027 6000 3184`
  (3-D Secure), `4000 0000 0000 0341` (attaches, later charges fail). **Test clocks** (Billing →
  Test clocks) simulate time: trial end → paid → failed → recovered → cancelled.
