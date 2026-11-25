import { afterEach, describe, expect, it, vi } from "vitest";

import { clientIp, hit, resetForTests } from "./ratelimit";
import { contentSecurityPolicy, securityHeaders } from "./security";

afterEach(() => {
  vi.unstubAllEnvs();
  resetForTests();
});

describe("rate limit", () => {
  it("allows `limit` requests per minute per IP, then 429 with a Retry-After", () => {
    const t0 = 1_000_000;
    for (let i = 0; i < 3; i++) expect(hit("1.2.3.4", t0 + i, 3).ok).toBe(true);
    const v = hit("1.2.3.4", t0 + 10_000, 3);
    expect(v).toEqual({ ok: false, retryAfterS: 50 });
    expect(hit("5.6.7.8", t0 + 10_000, 3).ok).toBe(true); // other IPs unaffected
    expect(hit("1.2.3.4", t0 + 60_001, 3).ok).toBe(true); // next window
  });
  it("takes the client IP from Railway's headers", () => {
    expect(clientIp(new Headers({ "x-real-ip": "9.9.9.9", "x-forwarded-for": "1.1.1.1" }))).toBe(
      "9.9.9.9",
    );
    expect(clientIp(new Headers({ "x-forwarded-for": "1.1.1.1, 10.0.0.1" }))).toBe("1.1.1.1");
    expect(clientIp(new Headers())).toBe("unknown");
  });
});

describe("security headers", () => {
  it("CSP has no unsafe-eval, forbids framing and stays same-origin", () => {
    const csp = contentSecurityPolicy(true);
    expect(csp).not.toContain("unsafe-eval");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("default-src 'self'");
    expect(csp).toContain("upgrade-insecure-requests");
    expect(contentSecurityPolicy(false)).not.toContain("upgrade-insecure-requests");
  });
  it("defaults: report-only CSP, noindex, no HSTS", () => {
    vi.stubEnv("NODE_ENV", "production");
    const h = securityHeaders(true);
    expect(h["Content-Security-Policy-Report-Only"]).toBeDefined();
    expect(h["Content-Security-Policy"]).toBeUndefined();
    expect(h["X-Robots-Tag"]).toBe("noindex, nofollow");
    expect(h["Strict-Transport-Security"]).toBeUndefined();
    expect(h["X-Content-Type-Options"]).toBe("nosniff");
    expect(h["Referrer-Policy"]).toBe("strict-origin-when-cross-origin");
  });
  it("go-live switches: enforce CSP, HSTS, indexing", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("CSP_MODE", "enforce");
    vi.stubEnv("HSTS_ENABLED", "true");
    vi.stubEnv("INDEXING_ENABLED", "true");
    const h = securityHeaders(true);
    expect(h["Content-Security-Policy"]).toContain("frame-ancestors 'none'");
    expect(h["Strict-Transport-Security"]).toBe("max-age=31536000; includeSubDomains");
    expect(h["X-Robots-Tag"]).toBeUndefined();
  });
});
