"use client";

import Link from "next/link";

import { useBilling } from "@/lib/billing/client";

const linkBtn =
  "inline-flex min-h-9 items-center justify-center rounded-[10px] bg-brand px-3.5 text-[13px] font-semibold whitespace-nowrap text-white no-underline hover:bg-brand-hover hover:text-white";

/**
 * "Start 7-day free trial" in the Premium teasers (v2 Phase 10 B3/B5). Signed out → create an
 * account first, then the pricing page (where checkout starts); signed in and allowed to
 * subscribe or not → the pricing page, which shows the renewal terms next to the checkout
 * button (v2 Part 2 §4) or explains why checkout isn't open (test-mode gate, email).
 */
export function TrialButton() {
  const { isPending, signedIn, billing } = useBilling();
  if (isPending) return <span aria-hidden className="block h-9 w-44" />;
  if (!signedIn) {
    return (
      <Link href="/signin?mode=signup&next=%2Fpricing" className={linkBtn}>
        Start 7-day free trial
      </Link>
    );
  }
  // Signed in: the pricing page, where the renewal terms sit next to the checkout button (ROSCA),
  // never straight to Stripe from a teaser.
  return (
    <Link href="/pricing" className={linkBtn}>
      {billing.trialEligible ? "Start 7-day free trial" : "See Premium"}
    </Link>
  );
}
