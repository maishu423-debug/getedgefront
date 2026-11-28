"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { openPortal, useBilling } from "@/lib/billing/client";
import { formatDay } from "@/lib/billing/format";

/**
 * Site-wide billing notices from the server-computed session (v2 Phase 10 B1, CONTEXT V2.4).
 * Fixed to the bottom of the window, so they never move the page (no layout shift); not shown
 * on /account, which explains everything in full.
 * - past_due (Premium continues while Stripe retries): "Payment failed. Update your card to keep
 *   Premium." with a button to the Stripe Customer Portal.
 * - cancelled, period not over (state "canceling"): a small "Premium until {date}" note.
 */
export function PastDueBanner() {
  const { billing } = useBilling();
  const path = usePathname();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  if (path === "/account") return null;
  if (billing.state === "past_due") {
    return (
      <div
        role="alert"
        className="fixed inset-x-0 bottom-0 z-40 flex flex-wrap items-center justify-center gap-x-3 gap-y-1 border-t border-[#F3C7C2] bg-[#FDECEA] px-4 py-3 text-center text-sm text-[#8E1F14] shadow-[0_-6px_18px_rgba(16,26,28,.08)]"
      >
        <span>Payment failed. Update your card to keep Premium.</span>
        <button
          type="button"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setFailed(false);
            const err = await openPortal();
            if (err) {
              setFailed(true);
              setBusy(false);
            }
          }}
          className="inline-flex min-h-9 cursor-pointer items-center rounded-[8px] border border-[#8E1F14] bg-white px-3 font-semibold text-[#8E1F14] focus-visible:ring-2 focus-visible:ring-[#8E1F14]/40 focus-visible:outline-none"
        >
          {busy ? "Opening…" : "Update card"}
        </button>
        {failed ? (
          <Link href="/account" className="font-semibold text-[#8E1F14] underline">
            Couldn&apos;t open billing; go to your account
          </Link>
        ) : null}
      </div>
    );
  }
  if (billing.state === "canceling" && billing.premiumUntil) {
    return (
      <div
        role="status"
        data-testid="premium-until"
        className="fixed right-3 bottom-3 z-40 rounded-full border border-border bg-surface px-3.5 py-1.5 text-[12.5px] text-text-2 shadow-[0_4px_14px_rgba(16,26,28,.12)]"
      >
        Premium until {formatDay(billing.premiumUntil)} ·{" "}
        <Link href="/account" className="font-semibold">
          Resume
        </Link>
      </div>
    );
  }
  return null;
}
