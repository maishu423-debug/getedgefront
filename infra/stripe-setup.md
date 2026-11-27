# Billing: Stripe setup (v2 Phase 8) — TEST MODE ONLY

What you (the owner) set up so Premium subscriptions work. Everything here is **test mode**
until Phase 11: production also runs with test keys, so nobody can pay real money yet. The
server refuses `sk_live_` keys unless `STRIPE_ALLOW_LIVE=true` (set only in Phase 11).

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
4. **Stripe Tax, collection OFF** — Settings → Tax (<https://dashboard.stripe.com/settings/tax>)
   → *Get started*: confirm the head office address and pick a preset product tax code (ask your
   accountant; software-as-a-service codes are the usual choice). **Add no tax registrations**
   (Tax → Locations): without one, Stripe calculates zero tax. EdgeFront's Checkout only asks Stripe
   to calculate tax when `STRIPE_TAX_ENABLED=true`; it stays `false` until you decide otherwise.
5. **API key** — Developers → API keys: copy the **test** secret key (`sk_test_…`). Better: create
   a *restricted* test key with write access to Products, Prices, Customers, Checkout Sessions,
   Subscriptions, Customer portal, Webhook endpoints and Test clocks.
6. **Products, price, portal, webhook** — run the setup script (or let me run it with your test
   key in the repo's `.env`):

   ```sh
   cd apps/web
   STRIPE_SECRET_KEY=sk_test_... node scripts/stripe-setup.mjs \
     --site https://getedgefront.com \
     --webhook-url https://getedgefront.com/api/stripe/webhook
   ```

   It creates or verifies, and is safe to run again:
   - Product **EdgeFront Premium** and a monthly price of **$20.00 USD** (lookup key
     `edgefront_premium_monthly_usd`, tax exclusive).
   - **Customer Portal** configuration: update payment method, invoice history, cancel at period
     end (with a reason), **no** plan switching or quantity changes, no email editing; returns to
     `/account`.
   - **Webhook endpoint** on the URL above with exactly these events:
     `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`,
     `customer.subscription.deleted`, `customer.subscription.trial_will_end`, `invoice.paid`,
     `invoice.payment_failed` (API version pinned to `2026-11-18.endive`).

   It prints `STRIPE_PRICE_ID`, `STRIPE_PORTAL_CONFIGURATION_ID` and, the first time only,
   `STRIPE_WEBHOOK_SECRET` (Stripe shows it once; lost → Developers → Webhooks → Roll secret).
7. **Railway → web → Variables**, then Deploy:

   | Variable | Value | |
   |---|---|---|
   | `STRIPE_SECRET_KEY` | your `sk_test_…` / `rk_test_…` key | 🔒 |
   | `STRIPE_WEBHOOK_SECRET` | `whsec_…` from step 6 | 🔒 |
   | `STRIPE_PRICE_ID` | `price_…` from step 6 | |
   | `STRIPE_PORTAL_CONFIGURATION_ID` | `bpc_…` from step 6 | |
   | `STRIPE_TAX_ENABLED` | `false` | |

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
