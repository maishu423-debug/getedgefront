import "server-only";

import { createHash } from "node:crypto";

import { betterAuth } from "better-auth";
import { APIError, createAuthMiddleware } from "better-auth/api";
import { nextCookies } from "better-auth/next-js";
import { customSession, genericOAuth } from "better-auth/plugins";
import { Pool } from "pg";

import { sqlStore } from "@/lib/billing/store";
import { getStripe } from "@/lib/billing/stripe";
import { billingSummary } from "@/lib/billing/summary";
import { logJson } from "@/lib/deploy";
import { sharedSqlite } from "@/lib/sqlite";

import { COMMON_PASSWORDS } from "./common-passwords";
import { sendEmail } from "./email";
import { PASSWORD_MAX, PASSWORD_MESSAGES, PASSWORD_MIN, passwordProblem } from "./password";
import * as T from "./templates";

/**
 * Better Auth for EdgeFront (v2 Phase 7). Tables live in Postgres schema `auth`, created by
 * Alembic migration 0007 (never by Better Auth's CLI). Locally (SQLite, owner rule: no local
 * Postgres) the same tables sit in the dev SQLite file shared with the API.
 */

const DAY = 24 * 60 * 60;

/** Same DATABASE_URL as the Python services (SQLAlchemy form or Railway's postgresql://). */
function database() {
  const url = process.env.DATABASE_URL ?? "";
  if (/^postgres(ql)?(\+psycopg)?:\/\//.test(url)) {
    return new Pool({
      connectionString: url.replace(/^postgres(ql)?(\+psycopg)?:\/\//, "postgresql://"),
      options: "-c search_path=auth", // Better Auth's tables are in schema `auth`
      max: 5,
    });
  }
  if (url.startsWith("sqlite:///")) {
    // Local dev and tests only: the one connection shared with billing (see lib/sqlite.ts).
    return sharedSqlite(url.slice("sqlite:///".length));
  }
  throw new Error("DATABASE_URL must be a postgresql:// or sqlite:/// URL");
}

export function siteUrl(): string {
  return (
    process.env.BETTER_AUTH_URL ??
    process.env.NEXT_PUBLIC_SITE_URL ??
    "http://localhost:3000"
  ).replace(/\/+$/, "");
}

/** Origins allowed to call the auth endpoints (CSRF/origin check, redirect targets). */
export function trustedOrigins(): string[] {
  const list = [
    "http://localhost:3000",
    "https://getedgefront.com",
    "https://www.getedgefront.com",
    siteUrl(),
  ];
  if (process.env.RAILWAY_PUBLIC_DOMAIN) list.push(`https://${process.env.RAILWAY_PUBLIC_DOMAIN}`);
  for (const o of (process.env.AUTH_EXTRA_TRUSTED_ORIGINS ?? "").split(","))
    if (o.trim()) list.push(o.trim());
  return [...new Set(list)];
}

/** Non-identifying reference for logs (never the email or the raw id). */
const ref = (id: string) => createHash("sha256").update(id).digest("hex").slice(0, 12);

// ---------------------------------------------------------------- per-email rate limits

/** [window seconds, max requests] per email address, on top of Better Auth's per-IP limits. */
const PER_EMAIL: Record<string, [number, number]> = {
  "/sign-in/email": [15 * 60, 10],
  "/sign-up/email": [60 * 60, 3],
  "/request-password-reset": [60 * 60, 3],
  "/send-verification-email": [60 * 60, 3],
};

type Adapter = {
  findOne: <T>(q: { model: string; where: { field: string; value: unknown }[] }) => Promise<T | null>;
  create: (q: { model: string; data: Record<string, unknown> }) => Promise<unknown>;
  update: (q: { model: string; where: { field: string; value: unknown }[]; update: Record<string, unknown> }) => Promise<unknown>;
}; // prettier-ignore

async function perEmailLimit(adapter: Adapter, path: string, email: string): Promise<void> {
  const rule = PER_EMAIL[path];
  if (!rule) return;
  const [windowS, max] = rule;
  const key = `email:${createHash("sha256").update(email.trim().toLowerCase()).digest("hex")}:${path}`;
  const now = Date.now();
  const row = await adapter.findOne<{ count: number; lastRequest: number }>({
    model: "rateLimit",
    where: [{ field: "key", value: key }],
  });
  if (!row) {
    await adapter.create({ model: "rateLimit", data: { key, count: 1, lastRequest: now } });
    return;
  }
  const windowStart = Number(row.lastRequest);
  if (now - windowStart > windowS * 1000) {
    await adapter.update({
      model: "rateLimit",
      where: [{ field: "key", value: key }],
      update: { count: 1, lastRequest: now },
    });
    return;
  }
  if (row.count >= max) {
    const retry = Math.max(1, Math.ceil((windowStart + windowS * 1000 - now) / 1000));
    logJson("warn", "auth rate limited (per email)", { path, retry_after_s: retry });
    throw new APIError("TOO_MANY_REQUESTS", {
      message: "Too many attempts. Please wait a few minutes and try again.",
    }, { "Retry-After": String(retry) }); // prettier-ignore
  }
  await adapter.update({
    model: "rateLimit",
    where: [{ field: "key", value: key }],
    update: { count: row.count + 1 },
  });
}

/** Per-IP limits on the auth endpoints: [window seconds, max requests]. */
const IP_RULES: Record<string, [number, number]> = {
  "/sign-in/email": [60, 10],
  "/sign-up/email": [60 * 60, 10],
  "/request-password-reset": [60 * 60, 10],
  "/send-verification-email": [60 * 60, 10],
  "/reset-password": [60 * 60, 20],
  "/change-password": [60 * 60, 10],
  "/delete-user": [60 * 60, 5],
  // A cheap read the header makes on every page view; generous so people behind one shared
  // address (offices, mobile carriers) are never shown as signed out.
  "/get-session": [60, 600],
};

/**
 * The end-to-end fake Google (e2e/fake-google.mjs) lets anyone sign in as anyone, so it is only
 * accepted on localhost and never on Railway; anything else stops the server at start-up.
 */
export function e2eFakeGoogleUrl(env: Record<string, string | undefined> = process.env) {
  const url = env.E2E_FAKE_GOOGLE_URL;
  if (!url) return null;
  const host = URL.canParse(url) ? new URL(url).hostname : "";
  if (env.RAILWAY_ENVIRONMENT_NAME || !["localhost", "127.0.0.1", "[::1]"].includes(host)) {
    throw new Error("E2E_FAKE_GOOGLE_URL is for local end-to-end tests only");
  }
  return url;
}

/** End-to-end tests run every user from one IP; they scale the per-IP limits up (only in a local
 * test run). Per-email limits are never scaled. */
function ipScale(): number {
  const n = Number(process.env.AUTH_TEST_IP_LIMIT_SCALE ?? "1");
  return process.env.NODE_ENV !== "production" || e2eFakeGoogleUrl() ? Math.max(1, n) : 1;
}

// ---------------------------------------------------------------- deletion hook (Phase 8)

/** Subscription statuses that still bill or grant access, so they must end with the account. */
const LIVE_STATUSES = new Set(["trialing", "active", "past_due", "unpaid", "incomplete", "paused"]);

/**
 * Runs before an account is deleted: cancels every live subscription immediately through Stripe
 * (no further charges), and refuses the deletion if that fails. The Stripe customer itself is
 * kept in Stripe for invoices and the law; our billing rows go with the account (FK cascade).
 */
export async function beforeAccountDeletion(user: { id: string; email: string }): Promise<void> {
  const subs = (await sqlStore().subscriptionsOf(user.id)).filter((s) =>
    LIVE_STATUSES.has(s.status),
  );
  if (!subs.length) return;
  try {
    const stripe = getStripe();
    for (const s of subs) {
      try {
        await stripe.subscriptions.cancel(s.id, {}, { idempotencyKey: `delete-account:${s.id}` });
      } catch (err) {
        // Already gone or already canceled at Stripe: fine. Anything else: stop.
        const code = (err as { code?: string }).code;
        if (code !== "resource_missing") throw err;
      }
    }
    logJson("info", "subscriptions canceled for account deletion", {
      user_ref: ref(user.id),
      count: subs.length,
    });
  } catch (err) {
    logJson("error", "account deletion blocked: subscription cancel failed", {
      user_ref: ref(user.id),
      error: err instanceof Error ? err.message : "unknown",
    });
    throw new APIError("BAD_GATEWAY", {
      message:
        "We couldn't cancel your subscription, so your account was not deleted. Please try again in a minute.",
      code: "SUBSCRIPTION_CANCEL_FAILED",
    });
  }
}

const NO_OAUTH_TOKENS = {
  accessToken: null,
  refreshToken: null,
  idToken: null,
  accessTokenExpiresAt: null,
  refreshTokenExpiresAt: null,
};

// ---------------------------------------------------------------- the instance

function build() {
  const fakeGoogle = e2eFakeGoogleUrl(); // tests only: a local fake OAuth server
  const google = !fakeGoogle && process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET;
  const plugins = [];
  if (fakeGoogle) {
    plugins.push(
      genericOAuth({
        config: [
          {
            providerId: "google",
            clientId: "e2e-client",
            clientSecret: "e2e-secret",
            authorizationUrl: `${fakeGoogle}/authorize`,
            tokenUrl: `${fakeGoogle}/token`,
            userInfoUrl: `${fakeGoogle}/userinfo`,
            scopes: ["openid", "email", "profile"],
            pkce: true,
          },
        ],
      }),
    );
  }

  return betterAuth({
    appName: "EdgeFront",
    baseURL: siteUrl(),
    secret: process.env.BETTER_AUTH_SECRET,
    database: database(),
    trustedOrigins: trustedOrigins(),
    telemetry: { enabled: false },
    // Better Auth logs some events (e.g. sign-up for an existing email) with the address at
    // "info": keep personal data out of production logs.
    logger: { level: process.env.NODE_ENV === "production" ? "warn" : "info" },

    emailAndPassword: {
      enabled: true,
      minPasswordLength: PASSWORD_MIN,
      maxPasswordLength: PASSWORD_MAX,
      // Browsing works unverified; Phase 8 requires a verified email before checkout. No session
      // is created at sign-up, so sign-up answers identically for new and existing emails.
      requireEmailVerification: false,
      autoSignIn: false,
      resetPasswordTokenExpiresIn: 60 * 60,
      revokeSessionsOnPasswordReset: true,
      sendResetPassword: async ({ user, url }) => sendEmail(T.resetPassword(user.email, url)),
      onPasswordReset: async ({ user }) =>
        sendEmail(T.passwordChanged(user.email, `${siteUrl()}/signin`)),
      onExistingUserSignUp: async ({ user }) =>
        sendEmail(
          T.existingAccount(user.email, `${siteUrl()}/signin`, `${siteUrl()}/reset-password`),
        ),
    },
    emailVerification: {
      sendOnSignUp: true,
      autoSignInAfterVerification: true,
      expiresIn: DAY,
      sendVerificationEmail: async ({ user, url }) => sendEmail(T.verifyEmail(user.email, url)),
    },

    socialProviders: google
      ? {
          google: {
            clientId: process.env.GOOGLE_CLIENT_ID!,
            clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
            prompt: "select_account",
            // default scopes are openid, email, profile — nothing more is requested
          },
        }
      : undefined,

    account: {
      accountLinking: {
        enabled: true,
        trustedProviders: [], // link only when the provider says the email is verified ...
        allowDifferentEmails: false,
        requireLocalEmailVerified: true, // ... and our account's email is verified too
      },
    },

    session: {
      expiresIn: 30 * DAY, // rolling: refreshed at most once a day while in use
      updateAge: DAY,
      freshAge: 10 * 60, // sensitive actions (delete account) need a sign-in from the last 10 min
    },

    rateLimit: {
      enabled: true,
      storage: "database", // survives deploys and restarts
      window: 60,
      max: 100 * ipScale(), // every other auth path
      customRules: Object.fromEntries(
        Object.entries(IP_RULES).map(([path, [window, max]]) => [
          path,
          { window, max: max * ipScale() },
        ]),
      ),
    },

    user: {
      deleteUser: {
        enabled: true,
        beforeDelete: async (user) => beforeAccountDeletion(user),
        afterDelete: async (user) => {
          logJson("info", "account deleted", { user_ref: ref(user.id) }); // audit, non-identifying
          await sendEmail(T.accountDeleted(user.email));
        },
      },
    },

    databaseHooks: {
      // Data minimisation: we don't keep the Google avatar URL (the UI shows initials).
      user: {
        create: { before: async (data) => ({ data: { ...data, image: null } }) },
        update: { before: async (data) => ({ data: { ...data, image: null } }) },
      },
      // Google is only used to prove who signs in: we never call Google APIs, so its access,
      // refresh and ID tokens are not stored (only provider + Google account id remain).
      account: {
        create: { before: async (data) => ({ data: { ...data, ...NO_OAUTH_TOKENS } }) },
        update: { before: async (data) => ({ data: { ...data, ...NO_OAUTH_TOKENS } }) },
      },
    },

    advanced: {
      useSecureCookies: process.env.NODE_ENV === "production" && siteUrl().startsWith("https://"),
      ipAddress: { ipAddressHeaders: ["x-real-ip", "x-forwarded-for"] },
    },

    hooks: {
      before: createAuthMiddleware(async (ctx) => {
        const body = (ctx.body ?? {}) as Record<string, unknown>;
        // Password rules: length is enforced by Better Auth, the common list here.
        const pw =
          ctx.path === "/sign-up/email"
            ? body.password
            : ctx.path === "/reset-password" || ctx.path === "/change-password"
              ? body.newPassword
              : undefined;
        if (typeof pw === "string" && passwordProblem(pw, COMMON_PASSWORDS) === "too_common") {
          throw new APIError("BAD_REQUEST", {
            message: PASSWORD_MESSAGES.too_common,
            code: "PASSWORD_TOO_COMMON",
          });
        }
        if (typeof body.email === "string" && PER_EMAIL[ctx.path]) {
          await perEmailLimit(ctx.context.adapter as unknown as Adapter, ctx.path, body.email);
        }
        // A password change always signs out every other session.
        if (ctx.path === "/change-password") {
          return { context: { body: { ...body, revokeOtherSessions: true } } };
        }
      }),
      after: createAuthMiddleware(async (ctx) => {
        if (ctx.path === "/change-password" && !(ctx.context.returned instanceof Error)) {
          const user = ctx.context.session?.user;
          if (user) await sendEmail(T.passwordChanged(user.email, `${siteUrl()}/signin`));
        }
      }),
    },

    plugins: [
      ...plugins,
      // Phase 8: the session also says what the user's plan is (computed on the server from
      // billing.subscriptions), so the header and pricing CTA need no extra request.
      customSession(async ({ user, session }) => ({
        user,
        session,
        billing: await billingSummary(user.id, user.email),
      })),
      nextCookies(), // must stay last
    ],
  });
}

type Auth = ReturnType<typeof build>;
let instance: Auth | null = null;

/** Lazily built: `next build` imports route modules but must never open the database. */
export function getAuth(): Auth {
  instance ??= build();
  return instance;
}

export function googleEnabled(): boolean {
  if (process.env.E2E_FAKE_GOOGLE_URL) return true;
  return Boolean(process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET);
}
