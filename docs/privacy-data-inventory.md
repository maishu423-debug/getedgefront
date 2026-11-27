# Personal data inventory (v2 Phase 7: accounts)

An engineering record of what personal data EdgeFront stores, where, why and for how long, for
whoever drafts the privacy policy (Q31). **This is not the privacy policy and contains no legal
text.** Update it whenever a phase adds or changes personal data.

Before Phase 7 the site stored no personal data: no accounts, no analytics, no cookies.

## 1. Stored in our database (Postgres, schema `auth`)

| Table | Personal data | Why | Kept until |
|---|---|---|---|
| `user` | name, email, whether the email is confirmed, created/updated times | the account; email is the sign-in name and where account emails go | account deletion |
| `session` | random session token, expiry, **IP address**, **browser user-agent**, created/updated times | keeps the user signed in (30-day rolling); IP and user-agent are recorded by Better Auth for security review | session expiry (30 days without use), sign-out, "sign out of all devices", password change/reset, account deletion. Expired rows are removed when looked up, not on a schedule (see §5) |
| `account` | for Google: Google's stable account id (`sub`); for email sign-in: the password **hash** (scrypt; the password itself is never stored) and when it was last changed | how the user signs in | the method is disconnected, or account deletion |
| `verification` | password-reset tokens, linked to the user (email-confirmation links are signed and expire after 24 h; they are not stored) | one-time reset links | link used or expired (1 h) |
| `rateLimit` | client IP address with the endpoint, or a SHA-256 hash of the email address, with counters | brute-force and abuse protection | overwritten as the window rolls (1 min to 1 h); rows are not swept (see §5) |

Not stored, by design:

- Google profile photo URL (removed before saving; the UI shows initials).
- Google access, refresh and ID tokens (removed before saving: we never call Google APIs).
- Plain passwords, card numbers or any card data, analytics or tracking identifiers.

Account deletion (`/account` → Delete account) removes the `user` row and, by cascade, all of
that user's sessions and sign-in methods, then sends a confirmation email. Pending
verification rows expire on their own.

## 1b. Billing (v2 Phase 8, Postgres schema `billing`)

| Table | Data | Why | Kept until |
|---|---|---|---|
| `customers` | our user id ↔ Stripe customer id; when the account's one free trial was used | reuse one Stripe customer per account; one trial per account | account deletion |
| `subscriptions` | Stripe subscription id, status, price id, period end, cancellation and trial dates, latest invoice status, the Stripe event id that last updated it | who is Premium (computed on the server from this mirror only) | account deletion |
| `webhook_events` | Stripe event id, type, received/processed times, error text (no personal data) | process each Stripe event once; debugging | not swept yet (see §5) |

We **never see or store card numbers** or other card data: Stripe's hosted Checkout and Customer
Portal collect them. The account page reads the card brand and last 4 digits from Stripe when it
is shown, to display them, and does not store them.

Deleting an account first cancels any live subscription immediately at Stripe (no further
charges), then deletes the account; our billing rows go with it. The **Stripe customer and its
invoices are kept at Stripe**, as payment records the law requires (retention is Stripe's and the
business's legal obligation, for the lawyer to describe).

## 2. Cookies

| Cookie | Content | Lifetime | Set when |
|---|---|---|---|
| `better-auth.session_token` (`__Secure-` prefix on HTTPS) | signed session token | 30 days, renewed daily while used | signing in |
| `better-auth.session_data`, `better-auth.dont_remember` | not set today (cookie cache and "remember me" are off); Better Auth only clears them on sign-out | — | — |
| OAuth `state` / PKCE cookies | random values | ~10 minutes | during "Continue with Google" |

All are HttpOnly, SameSite=Lax, Secure in production. No cookies are set for visitors who don't
sign in. No third-party or advertising cookies.

## 3. Third parties that receive personal data

| Who | What | Why |
|---|---|---|
| Google (OAuth) | the user's choice to sign in with Google; Google returns name, email, email-verified, account id | "Continue with Google" (scopes: openid, email, profile only) |
| Stripe (payments, processor) | the account's email and name (on the Stripe customer), our user id (metadata), and everything entered in Stripe Checkout / Customer Portal (card, billing address) | subscriptions, invoices, trial reminders, failed-payment emails |
| Resend (email delivery) | recipient email address and the email content (which includes one-time links) | sending account emails |
| Railway (hosting) | everything above, as our database and server host; request metadata in platform logs | hosting |
| Backup storage (Cloudflare R2 or Backblaze B2, owner's choice) | full database dumps, including the `auth` schema | disaster recovery; newest 14 daily + 8 weekly dumps kept, then deleted (infra/backup-restore.md). A deleted account can remain in backups until they age out (up to ~8 weeks) |

## 4. Logs

Application logs (Railway) never contain email addresses, names, passwords, tokens or links:

- account emails: only the kind (e.g. `verify`) and success/failure;
- per-email rate limiting: only the endpoint and retry time;
- account deletion: an audit line with a one-way hash of the user id (`user_ref`), no email;
- Better Auth's own logging is set to `warn` in production (its `info` level would log
  addresses for some events).

Railway's platform request logs may contain IP addresses and URLs (no tokens are put in URLs
except the one-time email links, which are spent on use).

## 5. Open items

- Expired `session` and `rateLimit` rows are not swept on a schedule; a nightly cleanup can be
  added to the worker's retention job if the tables grow (not needed at launch size).
- Data export (copy of my data) is not built; the account page shows everything stored except
  sessions.
- `billing.webhook_events` rows are not swept; a retention job can drop processed events older than e.g. 90 days.
- Q31: the privacy policy itself, and the delete-account copy on `/account`, are for the
  owner's lawyer.
