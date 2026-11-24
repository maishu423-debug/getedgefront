/** API response types, hand-kept in one place (CONTEXT.md §12). */

export interface ApiHealth {
  status: "ok" | "degraded";
  service: "api";
  db: "ok" | "unreachable";
  generated_at: string;
}
