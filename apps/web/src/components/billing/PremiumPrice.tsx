import { connection } from "next/server";

import { formatMoney } from "@/lib/billing/format";
import { premiumPrice } from "@/lib/billing/price";

/** The Premium price as Stripe has it (cached 10 min). Never invented: if Stripe can't be
 * reached, the page says so. Rendered at request time inside a fixed-height Suspense slot. */
export async function PremiumPrice() {
  await connection();
  const p = await premiumPrice();
  if (!p) {
    return (
      <div className="flex min-h-[84px] flex-col justify-center gap-1">
        <span className="text-sm text-text-2">The price isn&apos;t available right now.</span>
      </div>
    );
  }
  const short = formatMoney(p.unitAmount, p.currency, true);
  return (
    <div className="flex min-h-[84px] flex-col gap-1">
      <div className="flex items-baseline gap-1.5">
        <span className="font-display text-[40px] leading-none font-bold tracking-[-0.02em]">
          {short}
        </span>
        <span className="text-sm text-text-2">per {p.interval}</span>
      </div>
      <span className="text-sm text-text-2">
        Free for 7 days, then {short}/{p.interval} plus tax where applicable. Cancel anytime.
      </span>
    </div>
  );
}
