"use client";

import Link from "next/link";

import {
  CheckoutButton,
  ManageBillingButton,
  VerifyEmailPrompt,
} from "@/components/billing/BillingButtons";
import { useBilling } from "@/lib/billing/client";

const linkBtn =
  "inline-flex min-h-10 items-center self-start rounded-[10px] bg-brand px-4 text-sm font-semibold text-white no-underline hover:bg-brand-hover hover:text-white";

/**
 * Premium call to action (v2 Phase 8 B3/B7), from the server-computed session:
 * signed out → sign in and come back; email not confirmed → confirm first (resend);
 * Premium → "You're on Premium" + Manage billing; else "Start 7-day free trial" (first time) or
 * "Subscribe" (trial already used). Fixed minimum height while the session loads: no shift.
 */
export function PricingCta({ testModeGate = false }: { testModeGate?: boolean }) {
  const { isPending, signedIn, emailVerified, email, billing } = useBilling();
  if (isPending) return <span aria-hidden className="block h-10 w-48" />;
  // While Stripe is in test mode only allow-listed accounts may subscribe (owner decision).
  if (!signedIn && testModeGate) return <ComingSoon />;
  if (!signedIn) {
    return (
      <Link href="/signin?next=%2Fpricing" className={linkBtn}>
        Start 7-day free trial
      </Link>
    );
  }
  if (billing.tier === "premium") {
    return (
      <div className="flex flex-col items-start gap-2">
        <span className="font-semibold text-[#145F38]">You&apos;re on Premium</span>
        <ManageBillingButton />
      </div>
    );
  }
  if (!billing.billingEnabled || !billing.checkoutAllowed) return <ComingSoon />;
  if (!emailVerified) return <VerifyEmailPrompt email={email} />;
  return <CheckoutButton label={billing.trialEligible ? "Start 7-day free trial" : "Subscribe"} />;
}

function ComingSoon() {
  return (
    <span className="inline-flex min-h-10 items-center self-start rounded-[10px] bg-[#E7EAE6] px-4 text-sm font-semibold text-muted">
      Premium is coming soon
    </span>
  );
}
