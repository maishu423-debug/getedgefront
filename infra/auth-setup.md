# Accounts: owner setup (v2 Phase 7)

What you (the owner) set up by hand so sign-in works: the Google OAuth client, Resend email
with DNS on Namecheap, and the `web` variables on Railway. Nothing here is needed for local
development or CI: both use console/file email and a fake Google.

Production is **not** switched on by Phase 7. Do these steps when you approve the merge.

---

## 1. Secrets and variables (web service on Railway)

Settings → Variables on **web**, then **Deploy**. 🔒 = secret.

| Variable | Value | |
|---|---|---|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (type it literally: a reference variable) | 🔒 |
| `BETTER_AUTH_SECRET` | 32+ random bytes, e.g. the output of `openssl rand -base64 48` | 🔒 |
| `BETTER_AUTH_URL` | `https://<generated>.up.railway.app` now; `https://getedgefront.com` after go-live | |
| `GOOGLE_CLIENT_ID` | from §2 | |
| `GOOGLE_CLIENT_SECRET` | from §2 | 🔒 |
| `RESEND_API_KEY` | from §3 (a "Sending access" key for getedgefront.com only) | 🔒 |
| `EMAIL_FROM` | `EdgeFront <no-reply@getedgefront.com>` | |
| `INTERNAL_API_TOKEN` | 32+ random bytes; set the **same value on api** | 🔒 |

And on **api**: `INTERNAL_API_TOKEN` (same value as web). Without it every
`/api/v1/internal/*` route answers 403 (fails closed); public routes are unaffected.

Notes:

- `BETTER_AUTH_SECRET` signs sessions and email links. Changing it signs everyone out and
  invalidates links already sent. Never reuse it anywhere else.
- Allowed origins are built in: `http://localhost:3000`, `https://getedgefront.com`,
  `https://www.getedgefront.com`, `BETTER_AUTH_URL`, and the Railway domain (Railway provides
  `RAILWAY_PUBLIC_DOMAIN` automatically). Add more, comma-separated, in
  `AUTH_EXTRA_TRUSTED_ORIGINS` only if you ever need to.
- Never set `E2E_FAKE_GOOGLE_URL`, `EMAIL_OUTBOX_FILE` or `AUTH_TEST_IP_LIMIT_SCALE` on
  Railway. They are for local tests; the server refuses to start with the fake Google on
  Railway or on any host other than localhost.
- If `RESEND_API_KEY` is missing on Railway, emails fail with an error in the logs (they are
  never printed to the logs instead), so sign-up cannot be completed: set it before launch.

## 2. Google OAuth client

1. <https://console.cloud.google.com/> → create a project "EdgeFront" (or reuse one).
2. **APIs & Services → OAuth consent screen** (Google Auth Platform → Branding/Audience):
   - User type **External**. App name "EdgeFront", support email: your address, logo optional.
   - Authorized domain: `getedgefront.com` (add the Railway domain only if Google accepts it;
     the `up.railway.app` domain is shared, so it usually does not: test on localhost instead).
   - App home page `https://getedgefront.com`, privacy policy and terms links: the
     `/privacy` and `/terms` pages (they must exist before you publish the app, see Q31).
   - Scopes: only `openid`, `.../auth/userinfo.email`, `.../auth/userinfo.profile`. These are
     non-sensitive: no Google verification review is needed.
   - Publishing status: leave **Testing** and add yourself (and any testers) under **Test
     users**. Only test users can sign in while in Testing.
3. **Credentials → Create credentials → OAuth client ID → Web application**, name "EdgeFront web".
   - Authorized JavaScript origins: `http://localhost:3000`, `https://getedgefront.com`,
     `https://www.getedgefront.com`.
   - Authorized redirect URIs (exactly, no trailing slash):
     - `http://localhost:3000/api/auth/callback/google`
     - `https://getedgefront.com/api/auth/callback/google`
     - `https://www.getedgefront.com/api/auth/callback/google`
     - `https://<generated>.up.railway.app/api/auth/callback/google` (if Google accepts it)
4. Copy the client ID and secret into the Railway variables (§1) and into your local `.env`.
5. At go-live: **Publish app** (Audience → In production). With only the three basic scopes this
   is immediate.

### Testing real Google sign-in locally (no staging environment)

Google accepts `http://localhost:3000` redirect URIs while the consent screen is in Testing,
so real Google sign-in is tested by hand on your machine:

```sh
# apps/web/.env.local (never committed)
DATABASE_URL=sqlite:///C:/path/to/dev.db         # migrated with: uv run python -m edgefront_core.migrate up head
BETTER_AUTH_SECRET=<any 32+ characters for local use only>
BETTER_AUTH_URL=http://localhost:3000
GOOGLE_CLIENT_ID=<from step 3>
GOOGLE_CLIENT_SECRET=<from step 3>
# no RESEND_API_KEY: emails are printed in the terminal
```

Then `pnpm --filter @edgefront/web dev`, open <http://localhost:3000/signin> and use
"Continue with Google" with a test-user account. Staging is to be revisited in Phase 11.

## 3. Resend (transactional email) and DNS on Namecheap

1. Create a Resend account (free tier: 3,000 emails/month, 100/day).
2. **Domains → Add domain** `getedgefront.com`, region closest to Railway (us-east-1).
3. Resend shows DNS records. In Namecheap → Domain List → getedgefront.com → **Advanced DNS**,
   add each one exactly as shown (Namecheap wants the host *without* the domain, e.g.
   `resend._domainkey`, `send`):
   - **DKIM**: TXT `resend._domainkey` → the long `p=...` value.
   - **SPF** for the bounce domain: MX `send` → `feedback-smtp.us-east-1.amazonses.com`
     priority 10, and TXT `send` → `v=spf1 include:amazonses.com ~all`.
     (These are on the `send.` subdomain, so they do not touch any SPF record on the root.)
   - **DMARC**: TXT `_dmarc` → `v=DMARC1; p=none; rua=mailto:<an address you read>`.
     Start with `p=none`; after two clean weeks of reports, move to `p=quarantine`.
4. Wait for Resend to show the domain **Verified** (minutes to a few hours).
5. **API keys → Create** with "Sending access" restricted to `getedgefront.com`. Put it in
   `RESEND_API_KEY` on Railway (web). Set `EMAIL_FROM` as in §1.
6. Check: sign up on the Railway URL with your own address; the confirmation should arrive and
   pass SPF/DKIM/DMARC ("Show original" in Gmail).

Emails sent: confirm email, reset password (link valid 1 hour), password changed,
account deleted, and "you already have an account" (sent instead of creating a duplicate).

## 4. Restricted database role: skipped (documented decision)

The plan suggested giving `web` a Postgres role that can only touch the `auth` schema. It is
skipped for now:

- Railway's Postgres service has one managed user, and `${{Postgres.DATABASE_URL}}` always
  carries it. A second role would need its own password created by hand in SQL and a
  hand-written connection URL on `web`, which Railway would neither rotate nor update when it
  changes the database's credentials or host, so it is easy to break silently.
- Alembic (run by `api`) creates and owns the auth tables, so the role would also need default
  privileges maintained across migrations.

What protects the data instead: the auth tables live in their own `auth` schema; `web`
connects with `search_path=auth` and only ever queries Better Auth's tables there; the weather
data stays behind the API. Revisit in Phase 11 together with staging. The SQL would be:

```sql
CREATE ROLE edgefront_web LOGIN PASSWORD '<generated>';
GRANT USAGE ON SCHEMA auth TO edgefront_web;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA auth TO edgefront_web;
ALTER DEFAULT PRIVILEGES IN SCHEMA auth GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO edgefront_web;
```

## 5. Running the auth tests locally

No Docker, no Postgres (SQLite locally; Postgres runs in CI's `auth` job).

```sh
uv run python -m edgefront_core.migrate up head      # with DATABASE_URL=sqlite:///.../dev.db
pnpm --filter @edgefront/web build
# start the API (uvicorn) and the web server with test-only settings:
EMAIL_OUTBOX_FILE=/tmp/outbox.jsonl E2E_FAKE_GOOGLE_URL=http://localhost:4455 \
AUTH_TEST_IP_LIMIT_SCALE=100 RATE_LIMIT_PER_MINUTE=100000 BETTER_AUTH_SECRET=<local> \
BETTER_AUTH_URL=http://localhost:3000 DATABASE_URL=sqlite:///.../dev.db pnpm --filter @edgefront/web start
E2E_EMAIL_OUTBOX=/tmp/outbox.jsonl pnpm --filter @edgefront/web exec playwright test e2e/auth.spec.ts
```

Playwright starts the fake Google (`e2e/fake-google.mjs`) itself. Real Google is never
contacted by tests.
