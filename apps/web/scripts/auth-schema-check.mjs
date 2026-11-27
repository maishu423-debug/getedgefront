// Asks Better Auth whether the tables Alembic created (migration 0007) are what it needs.
//   DATABASE_URL=... node scripts/auth-schema-check.mjs
// Exits 1 if Better Auth would create a table or add a column. Run in CI on Postgres.
import { getMigrations } from "better-auth/db/migration";

const url = process.env.DATABASE_URL ?? "";
let database;
if (/^postgres(ql)?(\+psycopg)?:\/\//.test(url)) {
  const { Pool } = await import("pg");
  database = new Pool({
    connectionString: url.replace(/^postgres(ql)?(\+psycopg)?:\/\//, "postgresql://"),
    options: "-c search_path=auth",
  });
} else if (url.startsWith("sqlite:///")) {
  const { DatabaseSync } = await import("node:sqlite");
  database = new DatabaseSync(url.slice("sqlite:///".length));
} else {
  console.error("DATABASE_URL must be postgresql:// or sqlite:///");
  process.exit(2);
}

// Only the options that change the schema (keep in sync with src/lib/auth/server.ts).
const { toBeCreated, toBeAdded } = await getMigrations({
  database,
  emailAndPassword: { enabled: true },
  rateLimit: { enabled: true, storage: "database" },
  user: { deleteUser: { enabled: true } },
  telemetry: { enabled: false },
});
const problems = [
  ...toBeCreated.map((t) => `missing table ${t.table}`),
  ...toBeAdded.map((t) => `missing columns in ${t.table}: ${Object.keys(t.fields).join(", ")}`),
];
if (database.end) await database.end();
if (problems.length) {
  console.error("Better Auth schema drift:\n" + problems.join("\n"));
  process.exit(1);
}
console.log("auth schema matches Better Auth (no tables or columns to add)");
