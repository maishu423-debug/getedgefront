/**
 * Security headers for every page and route (Phase 6 B5).
 * The CSP fits Next.js and ECharts without `unsafe-eval`: Next's streamed RSC payload and
 * hydration use inline <script> tags, so script-src needs 'unsafe-inline' (nonces would force
 * every page to render dynamically and drop the prerendered shells); React and ECharts set
 * inline style attributes, so style-src needs 'unsafe-inline' too. Everything is same-origin:
 * fonts are self-hosted and the browser only talks to this site's /api/* proxy.
 */
import { cspMode, hstsEnabled, indexingEnabled } from "./deploy";

export function contentSecurityPolicy(https: boolean): string {
  return [
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    ...(https ? ["upgrade-insecure-requests"] : []),
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
    const name =
      cspMode() === "enforce" ? "Content-Security-Policy" : "Content-Security-Policy-Report-Only";
    h[name] = contentSecurityPolicy(https);
  }
  if (hstsEnabled()) h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains";
  if (!indexingEnabled()) h["X-Robots-Tag"] = "noindex, nofollow";
  return h;
}
