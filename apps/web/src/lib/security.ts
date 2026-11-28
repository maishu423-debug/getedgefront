/**
 * Security headers for every page and route (Phase 6 B5).
 * The CSP fits Next.js and ECharts without `unsafe-eval`: Next's streamed RSC payload and
 * hydration use inline <script> tags, so script-src needs 'unsafe-inline' (nonces would force
 * every page to render dynamically and drop the prerendered shells); React and ECharts set
 * inline style attributes, so style-src needs 'unsafe-inline' too. Everything is same-origin
 * (fonts self-hosted, the browser only talks to this site's /api/* proxy) except the Premium
 * live map's basemap (v2 Phase 10 B5): OpenFreeMap styles, tiles, glyphs and sprites, and MapLibre
 * runs a same-origin module worker (worker-src; blob: for its fallbacks).
 */
import { cspMode, hstsEnabled, indexingEnabled } from "./deploy";

/** `upgrade-insecure-requests` only takes effect in an enforced policy (browsers ignore it, with a
 * console warning, in report-only mode), so it is sent only when enforcing over HTTPS. */
/** Origins the live map may load from: OpenFreeMap, plus NEXT_PUBLIC_MAP_STYLE_URL's origin. */
export function mapOrigins(styleUrl = process.env.NEXT_PUBLIC_MAP_STYLE_URL ?? ""): string[] {
  const out = new Set(["https://tiles.openfreemap.org"]);
  try {
    if (styleUrl) {
      const u = new URL(styleUrl);
      if (u.protocol === "https:") out.add(u.origin);
    }
  } catch {
    // not a URL: the map falls back to the outline, nothing to allow
  }
  return [...out];
}

export function contentSecurityPolicy(https: boolean, enforce = true): string {
  const map = mapOrigins().join(" ");
  return [
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline'",
    "style-src 'self' 'unsafe-inline'",
    `img-src 'self' data: blob: ${map}`,
    "font-src 'self'",
    `connect-src 'self' ${map}`,
    "worker-src 'self' blob:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    ...(https && enforce ? ["upgrade-insecure-requests"] : []),
    "report-uri /api/csp-report",
  ].join("; ");
}

export function securityHeaders(https: boolean): Record<string, string> {
  const h: Record<string, string> = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
  };
  if (process.env.NODE_ENV === "production") {
    // `next dev` needs eval for fast refresh, so the policy is only sent by production builds.
    const enforce = cspMode() === "enforce";
    const name = enforce ? "Content-Security-Policy" : "Content-Security-Policy-Report-Only";
    h[name] = contentSecurityPolicy(https, enforce);
  }
  if (hstsEnabled()) h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains";
  if (!indexingEnabled()) h["X-Robots-Tag"] = "noindex, nofollow";
  return h;
}
