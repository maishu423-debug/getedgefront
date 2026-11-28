"use client";

import Link from "next/link";

import { useBilling } from "@/lib/billing/client";

import { CheckoutButton } from "./BillingButtons";

const linkBtn =
  "inline-flex min-h-9 items-center justify-center rounded-[10px] bg-brand px-3.5 text-[13px] font-semibold whitespace-nowrap text-white no-underline hover:bg-brand-hover hover:text-white";

/**
 * "Start 7-day free trial" in the Premium teasers (v2 Phase 10 B3/B5). Signed out → create an
 * account first, then the pricing page (where checkout starts); signed in and allowed to
 * subscribe → checkout; otherwise → the pricing page, which explains why not (test-mode gate,
 * email not confirmed).
 */
export function TrialButton() {
  const { isPending, signedIn, emailVerified, billing } = useBilling();
  if (isPending) return <span aria-hidden className="block h-9 w-44" />;
  if (!signedIn) {
    return (
      <Link href="/signin?mode=signup&next=%2Fpricing" className={linkBtn}>
        Start 7-day free trial
      </Link>
    );
  }
  if (billing.billingEnabled && billing.checkoutAllowed && emailVerified) {
    return (
      <CheckoutButton
        label={billing.trialEligible ? "Start 7-day free trial" : "Subscribe"}
        className="!min-h-9 !px-3.5 !text-[13px]"
      />
    );
  }
  return (
    <Link href="/pricing" className={linkBtn}>
      {billing.trialEligible ? "Start 7-day free trial" : "See Premium"}
    </Link>
  );
}
