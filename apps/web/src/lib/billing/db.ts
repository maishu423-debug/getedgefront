import "server-only";

import { NodeSqliteDialect } from "@better-auth/kysely-adapter/node-sqlite-dialect";
import { Kysely, PostgresDialect } from "kysely";
import { Pool } from "pg";

import { sharedSqlite } from "@/lib/sqlite";

/**
 * The billing tables (Alembic migration 0008). Postgres: schema `billing`, timestamptz, boolean.
 * SQLite (local only): main database, ISO text, 0/1. Writes always send ISO strings and real
 * booleans are converted here; reads go through `toDate` / `toBool`.
 */
export interface BillingTables {
  customers: {
    user_id: string;
    stripe_customer_id: string;
    trial_used_at: string | Date | null;
    created_at: string | Date;
  };
  subscriptions: {
    stripe_subscription_id: string;
    user_id: string;
    stripe_customer_id: string;
    status: string;
    price_id: string | null;
    current_period_end: string | Date | null;
    cancel_at_period_end: boolean | number;
    cancel_at: string | Date | null;
    trial_end: string | Date | null;
    canceled_at: string | Date | null;
    ended_at: string | Date | null;
    latest_invoice_status: string | null;
    updated_from_event_id: string | null;
    updated_at: string | Date;
  };
  webhook_events: {
    stripe_event_id: string;
    type: string;
    received_at: string | Date;
    processed_at: string | Date | null;
    error: string | null;
  };
}

interface Handle {
  db: Kysely<BillingTables>;
  postgres: boolean;
}

let handle: Handle | null = null;

function open(): Handle {
  const url = process.env.DATABASE_URL ?? "";
  if (/^postgres(ql)?(\+psycopg)?:\/\//.test(url)) {
    const pool = new Pool({
      connectionString: url.replace(/^postgres(ql)?(\+psycopg)?:\/\//, "postgresql://"),
      max: 3,
    });
    const db = new Kysely<BillingTables>({ dialect: new PostgresDialect({ pool }) });
    return { db: db.withSchema("billing"), postgres: true };
  }
  if (url.startsWith("sqlite:///")) {
    // Local only: the same connection Better Auth uses (see lib/sqlite.ts).
    const database = sharedSqlite(url.slice("sqlite:///".length));
    return {
      db: new Kysely<BillingTables>({ dialect: new NodeSqliteDialect({ database }) }),
      postgres: false,
    };
  }
  throw new Error("DATABASE_URL must be a postgresql:// or sqlite:/// URL");
}

/** Lazily opened: `next build` must never touch the database. */
export function billingDb(): Handle {
  handle ??= open();
  return handle;
}

/** A boolean as the current database stores it. */
export function dbBool(value: boolean): boolean | number {
  return billingDb().postgres ? value : value ? 1 : 0;
}

export function toDate(value: string | Date | null | undefined): Date | null {
  if (value == null) return null;
  const d = value instanceof Date ? value : new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

export const toBool = (value: boolean | number | null | undefined) => value === true || value === 1;

export const iso = (d: Date | null | undefined) => (d ? d.toISOString() : null);
