/** One vocabulary of data states for every block on the site (owner B2). */

export type UiState =
  | "ok"
  | "loading"
  | "no_data" // nothing stored yet
  | "stale" // data exists but is old (amber, with age)
  | "upstream_down" // the source is failing; show last good data + age
  | "not_available" // product not published for this station
  | "not_found"; // unknown station

export interface StateInput {
  /** The API request itself failed (FastAPI unreachable or 5xx). */
  requestFailed?: boolean;
  notFound?: boolean;
  /** API `status` field. */
  status?: "ok" | "no_data" | "stale" | "none_available" | "not_available" | "not_issued_yet";
  /** Source health from /status, when known. */
  sourceHealthy?: boolean | null;
  /** Whether stored data exists to show alongside a warning. */
  hasData?: boolean;
}

export function uiStateFor(i: StateInput): UiState {
  if (i.notFound) return "not_found";
  if (i.requestFailed) return "upstream_down";
  if (i.status === "not_available" || i.status === "none_available") return "not_available";
  if (i.status === "no_data" || i.status === "not_issued_yet") return "no_data";
  if (i.sourceHealthy === false) return i.hasData === false ? "no_data" : "upstream_down";
  if (i.status === "stale") return "stale";
  return "ok";
}

export const STATE_COPY: Record<Exclude<UiState, "ok" | "loading">, string> = {
  no_data: "No data received yet.",
  stale: "Stale",
  upstream_down: "Source not responding. Showing the last data received.",
  not_available: "Not published for this station.",
  not_found: "Station not found.",
};
