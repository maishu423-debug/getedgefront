/**
 * `?next=` handling (v2 Phase 7 B): only paths on this site are allowed, so the parameter can't
 * be used as an open redirect. Anything else falls back to `fallback`.
 */
const PLACEHOLDER = "https://edgefront.invalid";

export function safeNext(next: string | null | undefined, fallback = "/"): string {
  if (!next || typeof next !== "string") return fallback;
  const raw = next.trim();
  // A single-slash absolute path only: reject protocol-relative (//, /\), backslashes and
  // control characters before the URL parser can "repair" them into another host.
  if (!raw.startsWith("/") || raw.startsWith("//") || raw.startsWith("/\\")) return fallback;
  if (/[\\\u0000-\u001f\u007f]/.test(raw)) return fallback;
  let url: URL;
  try {
    url = new URL(raw, PLACEHOLDER);
  } catch {
    return fallback;
  }
  if (url.origin !== PLACEHOLDER) return fallback;
  if (url.pathname.startsWith("/api/")) return fallback; // never bounce into an API route
  return `${url.pathname}${url.search}${url.hash}`;
}
