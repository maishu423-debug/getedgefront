import "server-only";

import { DatabaseSync } from "node:sqlite";

/**
 * Local development and tests only (owner rule: no local Postgres): one SQLite connection per
 * process, shared by Better Auth and billing. node:sqlite is synchronous, so two connections in
 * the same process waiting on each other's locks would block the event loop (deadlock until
 * the busy timeout). WAL lets the API and worker processes read while we write.
 */
let shared: { path: string; db: DatabaseSync } | null = null;

export function sharedSqlite(path: string): DatabaseSync {
  if (shared && shared.path === path) return shared.db;
  const db = new DatabaseSync(path);
  db.exec("PRAGMA busy_timeout = 5000");
  db.exec("PRAGMA journal_mode = WAL");
  db.exec("PRAGMA foreign_keys = ON");
  shared = { path, db };
  return db;
}
