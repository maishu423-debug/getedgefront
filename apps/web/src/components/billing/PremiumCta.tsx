import { connection } from "next/server";

import { PricingCta } from "@/components/PricingCta";
import { testModeGate } from "@/lib/billing/allowlist";
import { premiumPrice } from "@/lib/billing/price";

/** The pricing CTA with the server's test-mode gate (request time, inside a Suspense slot). */
export async function PremiumCta() {
  await connection();
  const p = await premiumPrice();
  return <PricingCta testModeGate={testModeGate()} price={p} />;
}
