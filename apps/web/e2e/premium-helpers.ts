import { expect, type Page, type TestInfo } from "@playwright/test";

import { PASSWORD, signIn, signUp, uniqueEmail, verify } from "./auth-helpers";

/**
 * v2 Phase 10 e2e: users in every billing state, made by writing the billing mirror (the tables
 * our Stripe webhook keeps up to date) straight into the test database. Stripe is never called.
 * DATABASE_URL is the same database the web server uses: Postgres in CI, SQLite locally.
 */
export type BillingCase = "free" | "trialing" | "active" | "past_due" | "canceling" | "expired";

const DAY = 86_400_000;

type Sub = {
  status: string;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  trial_end: string | null;
  canceled_at: string | null;
  ended_at: string | null;
  latest_invoice_status: string | null;
};

function subscriptionFor(state: BillingCase, now: number): Sub | null {
  const at = (d: number) => new Date(now + d * DAY).toISOString();
  const base = { cancel_at_period_end: false, trial_end: null, canceled_at: null, ended_at: null, latest_invoice_status: "paid" }; // prettier-ignore
  switch (state) {
    case "free":
      return null;
    case "trialing":
      return { ...base, status: "trialing", current_period_end: at(5), trial_end: at(5), latest_invoice_status: null }; // prettier-ignore
    case "active":
      return { ...base, status: "active", current_period_end: at(20) };
    case "past_due":
      return { ...base, status: "past_due", current_period_end: at(20), latest_invoice_status: "open" }; // prettier-ignore
    case "canceling":
      return { ...base, status: "active", current_period_end: at(10), cancel_at_period_end: true, canceled_at: at(-1) }; // prettier-ignore
    case "expired":
      return { ...base, status: "canceled", current_period_end: at(-2), canceled_at: at(-12), ended_at: at(-2) }; // prettier-ignore
  }
}

type Db = {
  one: (sql: string, args: unknown[]) => Promise<Record<string, unknown> | undefined>;
  run: (sql: string, args: unknown[]) => Promise<void>;
  close: () => Promise<void>;
  pg: boolean;
};

async function openDb(): Promise<Db> {
  const url = process.env.DATABASE_URL ?? "";
  if (/^postgres(ql)?(\+psycopg)?:\/\//.test(url)) {
    const { Client } = await import("pg");
    const c = new Client({
      connectionString: url.replace(/^postgres(ql)?(\+psycopg)?:\/\//, "postgresql://"),
    });
    await c.connect();
    const n = (sql: string) => { let i = 0; return sql.replace(/\?/g, () => `$${++i}`); }; // prettier-ignore
    return {
      pg: true,
      one: async (sql, args) => (await c.query(n(sql), args)).rows[0],
      run: async (sql, args) => void (await c.query(n(sql), args)),
      close: () => c.end(),
    };
  }
  if (url.startsWith("sqlite:///")) {
    const { DatabaseSync } = await import("node:sqlite");
    const db = new DatabaseSync(url.slice("sqlite:///".length));
    db.exec("PRAGMA busy_timeout = 5000");
    const fix = (args: unknown[]) => args.map((a) => (typeof a === "boolean" ? (a ? 1 : 0) : a)) as never[];
    return {
      pg: false,
      one: async (sql, args) => db.prepare(sql).get(...fix(args)) as Record<string, unknown> | undefined,
      run: async (sql, args) => void db.prepare(sql).run(...fix(args)),
      close: async () => db.close(),
    };
  } // prettier-ignore
  throw new Error("set DATABASE_URL to the web server's database (postgresql:// or sqlite:///)");
}

/** Puts the user's subscription into `state` (and nothing else changes). */
export async function setBilling(email: string, state: BillingCase): Promise<void> {
  const db = await openDb();
  const t = (name: string) => (db.pg ? `billing.${name}` : name);
  const users = db.pg ? `auth."user"` : `"user"`;
  try {
    const u = await db.one(`SELECT id FROM ${users} WHERE email = ?`, [email]);
    if (!u) throw new Error(`no user ${email}`);
    const userId = String(u.id);
    const cus = `cus_e2e_${userId.slice(0, 12)}`;
    const sid = `sub_e2e_${userId.slice(0, 12)}`;
    const now = new Date().toISOString();
    await db.run(`DELETE FROM ${t("subscriptions")} WHERE user_id = ?`, [userId]);
    const sub = subscriptionFor(state, Date.now());
    if (!sub) return;
    if (!(await db.one(`SELECT user_id FROM ${t("customers")} WHERE user_id = ?`, [userId]))) {
      await db.run(
        `INSERT INTO ${t("customers")} (user_id, stripe_customer_id, trial_used_at, created_at) VALUES (?, ?, ?, ?)`,
        [userId, cus, now, now],
      );
    }
    await db.run(
      `INSERT INTO ${t("subscriptions")} (stripe_subscription_id, user_id, stripe_customer_id, status, price_id, current_period_end, cancel_at_period_end, cancel_at, trial_end, canceled_at, ended_at, latest_invoice_status, updated_from_event_id, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [sid, userId, cus, sub.status, "price_e2e_premium", sub.current_period_end, sub.cancel_at_period_end, null, sub.trial_end, sub.canceled_at, sub.ended_at, sub.latest_invoice_status, "evt_e2e_seed", now],
    ); // prettier-ignore
  } finally {
    await db.close();
  }
}

/** A new verified, signed-in account in `state`. Returns its email. */
export async function userIn(page: Page, info: TestInfo, state: BillingCase): Promise<string> {
  const email = uniqueEmail(info, `p10-${state}`);
  await signUp(page, "Premium Tester", email);
  await verify(page, email); // signs in
  await setBilling(email, state);
  return email;
}

export async function signInAs(page: Page, email: string): Promise<void> {
  await signIn(page, email, PASSWORD);
  await expect(page).not.toHaveURL(/\/signin/);
}

/** Every request the page makes, for leak checks. */
export function recordRequests(page: Page): string[] {
  const urls: string[] = [];
  page.on("request", (r) => urls.push(r.url()));
  return urls;
}

/** Never depend on OpenFreeMap in tests (owner B9): its hosts are refused. */
export async function blockOpenFreeMap(page: Page): Promise<void> {
  await page.route(/^https:\/\/tiles\.openfreemap\.org\//, (route) =>
    route.abort("blockedbyclient"),
  );
}

export const isPhone = (page: Page) => (page.viewportSize()?.width ?? 1440) < 640;
