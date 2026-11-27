/**
 * Who may start Checkout (v2 Phase 8, owner decision 2026-11-27). While Stripe runs in TEST mode
 * (also in production until Phase 11), only emails in BILLING_TEST_ALLOWLIST may subscribe;
 * everyone else sees "Premium is coming soon". Entries are comma- or space-separated: a full
 * address (owner@example.com) or a whole domain (@example.com). An empty list allows nobody.
 * With a live key the list no longer applies. Pure, so it is unit-tested.
 */

export function isTestModeKey(secretKey: string): boolean {
  return /^(sk|rk)_test_/.test(secretKey);
}

export function parseAllowlist(raw: string | undefined): string[] {
  return (raw ?? "")
    .split(/[\s,]+/)
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean);
}

export function checkoutAllowed(
  email: string,
  env: Record<string, string | undefined> = process.env,
): boolean {
  if (!isTestModeKey(env.STRIPE_SECRET_KEY ?? "")) return true; // live mode (Phase 11)
  const address = email.trim().toLowerCase();
  const domain = address.slice(address.lastIndexOf("@"));
  return parseAllowlist(env.BILLING_TEST_ALLOWLIST).some((entry) =>
    entry.startsWith("@") ? entry === domain : entry === address,
  );
}

/** True while checkout is limited to the allowlist (anonymous visitors see "coming soon"). */
export function testModeGate(env: Record<string, string | undefined> = process.env): boolean {
  return isTestModeKey(env.STRIPE_SECRET_KEY ?? "");
}
