// Checks that the billing tables Alembic created (migration 0008) have exactly the columns the
// web app's code uses (src/lib/billing/db.ts, BillingTables). Run in CI on Postgres:
//   DATABASE_URL=... node scripts/billing-schema-check.mjs
// Exits 1 on any missing or unexpected column.
const EXPECTED = {
  customers: ["user_id", "stripe_customer_id", "trial_used_at", "created_at"],
  subscriptions: [
    "stripe_subscription_id", "user_id", "stripe_customer_id", "status", "price_id",
    "current_period_end", "cancel_at_period_end", "cancel_at", "trial_end", "canceled_at",
    "ended_at", "latest_invoice_status", "updated_from_event_id", "updated_at",
  ],
  webhook_events: ["stripe_event_id", "type", "received_at", "processed_at", "error"],
}; // prettier-ignore

const url = process.env.DATABASE_URL ?? "";
const actual = {};
if (/^postgres(ql)?(\+psycopg)?:\/\//.test(url)) {
  const { Pool } = await import("pg");
  const pool = new Pool({
    connectionString: url.replace(/^postgres(ql)?(\+psycopg)?:\/\//, "postgresql://"),
  });
  const { rows } = await pool.query(
    "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = 'billing'",
  );
  for (const r of rows) (actual[r.table_name] ??= []).push(r.column_name);
  await pool.end();
} else if (url.startsWith("sqlite:///")) {
  const { DatabaseSync } = await import("node:sqlite");
  const db = new DatabaseSync(url.slice("sqlite:///".length));
  for (const t of Object.keys(EXPECTED)) {
    const cols = db.prepare(`PRAGMA table_info("${t}")`).all();
    if (cols.length) actual[t] = cols.map((c) => c.name);
  }
} else {
  console.error("DATABASE_URL must be postgresql:// or sqlite:///");
  process.exit(2);
}

const problems = [];
for (const [table, cols] of Object.entries(EXPECTED)) {
  const have = new Set(actual[table] ?? []);
  if (!actual[table]) problems.push(`missing table billing.${table}`);
  for (const c of cols)
    if (actual[table] && !have.has(c)) problems.push(`missing column ${table}.${c}`);
  for (const c of have) if (!cols.includes(c)) problems.push(`unexpected column ${table}.${c}`);
}
for (const t of Object.keys(actual))
  if (!EXPECTED[t]) problems.push(`unexpected table billing.${t}`);
if (problems.length) {
  console.error("Billing schema drift:\n" + problems.join("\n"));
  process.exit(1);
}
console.log("billing schema matches the web app (3 tables)");
