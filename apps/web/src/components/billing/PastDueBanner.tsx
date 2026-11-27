"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useBilling } from "@/lib/billing/client";

/**
 * Site-wide notice while a payment is failing (state past_due: Premium continues while Stripe
 * retries). Fixed to the bottom of the window, so it never moves the page (no layout shift).
 * Not shown on /account, which explains it in full.
 */
export function PastDueBanner() {
  const { billing } = useBilling();
  const path = usePathname();
  if (billing.state !== "past_due" || path === "/account") return null;
  return (
    <div
      role="alert"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-[#F3C7C2] bg-[#FDECEA] px-4 py-3 text-center text-sm text-[#8E1F14] shadow-[0_-6px_18px_rgba(16,26,28,.08)]"
    >
      Your last payment failed. Stripe will retry, and Premium continues for now.{" "}
      <Link href="/account" className="font-semibold text-[#8E1F14] underline">
        Update your card
      </Link>
    </div>
  );
}
