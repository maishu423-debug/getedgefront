import { describe, expect, it, vi } from "vitest";

import { initials } from "@/components/HeaderAccount";

import { PASSWORD_MAX, PASSWORD_MIN, passwordProblem } from "./password";
import { safeNext } from "./redirect";
import { existingAccount, resetPassword, verifyEmail } from "./templates";
import { FRESH_MS, viewerFromSession } from "./viewer";

vi.mock("server-only", () => ({}));
vi.mock("next/headers", () => ({ headers: async () => new Headers() }));
vi.mock("./server", () => ({ getAuth: () => ({}) }));
vi.mock("./client", () => ({ authClient: {} }));

describe("safeNext (?next= is same-site only)", () => {
  it.each([
    ["/station/KDFW", "/station/KDFW"],
    ["/account?tab=1#methods", "/account?tab=1#methods"],
    ["/pricing", "/pricing"],
    ["/a/../account", "/account"],
    ["/%0a/evil", "/%0a/evil"], // an encoded newline stays a harmless path on this site
  ])("keeps %s", (input, out) => expect(safeNext(input)).toBe(out));

  it.each([
    null,
    undefined,
    "",
    "https://evil.example.com/",
    "http://localhost:3000/account", // absolute URLs are refused even for this site
    "//evil.example.com",
    "/\\evil.example.com",
    "/\\/evil.example.com",
    "\\\\evil.example.com",
    "/foo\nbar",
    "/foo\tbar",
    "javascript:alert(1)",
    "evil.example.com",
    "/api/auth/sign-out",
    " //evil.example.com",
  ])("refuses %j", (input) => expect(safeNext(input as string | null)).toBe("/"));

  it("uses the fallback", () => expect(safeNext("//x", "/account")).toBe("/account"));
});

describe("passwordProblem", () => {
  const common = new Set(["password123", "qwertyuiop"]);
  it("enforces the length bounds in characters", () => {
    expect(passwordProblem("a".repeat(PASSWORD_MIN - 1))).toBe("too_short");
    expect(passwordProblem("a".repeat(PASSWORD_MIN))).toBeNull();
    expect(passwordProblem("a".repeat(PASSWORD_MAX + 1))).toBe("too_long");
    expect(passwordProblem("🌩️".repeat(5))).toBeNull(); // 10 code points
    expect(passwordProblem("😀".repeat(9))).toBe("too_short"); // 18 UTF-16 units, 9 characters
  });
  it("refuses common passwords regardless of case", () => {
    expect(passwordProblem("Password123", common)).toBe("too_common");
    expect(passwordProblem("QWERTYUIOP", common)).toBe("too_common");
    expect(passwordProblem("lighthouse-anemometer-42", common)).toBeNull();
  });
  it("ships a real common-password list", async () => {
    const { COMMON_PASSWORDS } = await import("./common-passwords");
    expect(COMMON_PASSWORDS.size).toBeGreaterThan(9_000);
    expect(passwordProblem("1234567890", COMMON_PASSWORDS)).toBe("too_common");
    expect([...COMMON_PASSWORDS].every((p) => p === p.toLowerCase() && p.length >= 10)).toBe(true);
  });
});

describe("viewerFromSession", () => {
  const user = { id: "u1", name: "Ada", email: "ada@example.org", emailVerified: true };
  const now = Date.parse("2026-11-26T12:00:00Z");

  it("anonymous without a session", () => {
    expect(viewerFromSession(null, now)).toMatchObject({
      user: null,
      tier: "anonymous",
      sessionCreatedAt: null,
      fresh: false,
    });
    expect(viewerFromSession(null, now).billing.tier).toBe("free");
  });
  it("tier comes only from the server-computed billing summary", () => {
    const base = { user, session: { createdAt: new Date(now) } };
    expect(viewerFromSession(base, now).tier).toBe("free"); // no summary: Free
    const summary = {
      tier: "premium" as const,
      state: "trialing" as const,
      premiumUntil: null,
      trialEnd: "2026-12-03T12:00:00.000Z",
      currentPeriodEnd: "2026-12-03T12:00:00.000Z",
      trialEligible: false,
      billingEnabled: true,
    };
    expect(viewerFromSession({ ...base, billing: summary }, now).tier).toBe("premium");
    expect(viewerFromSession({ ...base, billing: { ...summary, tier: "free" } }, now).tier).toBe(
      "free",
    );
  });
  it("free without a subscription, and fresh for 10 minutes", () => {
    const fresh = viewerFromSession({ user, session: { createdAt: new Date(now - 60_000) } }, now);
    expect(fresh.tier).toBe("free");
    expect(fresh.fresh).toBe(true);
    const old = viewerFromSession(
      { user, session: { createdAt: new Date(now - FRESH_MS).toISOString() } },
      now,
    );
    expect(old.fresh).toBe(false);
  });
  it("exposes only the fields the app needs", () => {
    const extra = { ...user, image: "x", banned: false } as typeof user;
    const v = viewerFromSession({ user: extra, session: { createdAt: new Date(now) } }, now);
    expect(Object.keys(v.user!).sort()).toEqual(["email", "emailVerified", "id", "name"]);
  });
});

describe("initials", () => {
  it.each([
    ["Ada Lovelace", "AL"],
    ["grace", "G"],
    ["Jean-Luc Picard", "JP"],
    ["ada.lovelace@example.org", "AL"],
    ["", "?"],
  ])("%j → %s", (name, out) => expect(initials(name)).toBe(out));
});

describe("email templates", () => {
  it("escape HTML and carry the link in both versions", () => {
    const url = 'https://getedgefront.com/x?a=1&b="2"';
    const m = verifyEmail("a@example.org", url);
    expect(m.kind).toBe("verify");
    expect(m.html).toContain("https://getedgefront.com/x?a=1&amp;b=&quot;2&quot;");
    expect(m.html).not.toContain('b="2"');
    expect(m.text).toContain(url);
  });
  it("existing-account email offers sign in and reset", () => {
    const m = existingAccount("a@example.org", "https://s/signin", "https://s/reset-password");
    expect(m.kind).toBe("existing_account");
    expect(m.text).toContain("https://s/signin");
    expect(m.text).toContain("https://s/reset-password");
  });
  it("reset email says it expires in an hour", () => {
    expect(resetPassword("a@example.org", "https://s/r").text).toMatch(/1 hour|one hour/i);
  });
});
