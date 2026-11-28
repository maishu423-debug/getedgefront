"use client";

import Link from "next/link";

import {
  CheckoutButton,
  ManageBillingButton,
  VerifyEmailPrompt,
} from "@/components/billing/BillingButtons";
import { useBilling } from "@/lib/billing/client";
import type { DisclosurePrice } from "@/lib/billing/disclosure";

import { AgreeLine, CheckoutDisclosure } from "./billing/CheckoutDisclosure";

const linkBtn =
  "inline-flex min-h-10 items-center self-start rounded-[10px] bg-brand px-4 text-sm font-semibold text-white no-underline hover:bg-brand-hover hover:text-white";

/**
 * Premium call to action (v2 Phase 8 B3/B7), from the server-computed session:
 * signed out → sign in and come back; email not confirmed → confirm first (resend);
 * Premium → "You're on Premium" + Manage billing; else "Start 7-day free trial" (first time) or
 * "Subscribe" (trial already used). Fixed minimum height while the session loads: no shift.
 */
export function PricingCta(props: {
  testModeGate?: boolean;
  /** from Stripe (server); the renewal terms are shown next to the button (ROSCA) */
  price?: DisclosurePrice | null;
}) {
  // The terms + button + agreement line appear once the session is known; their space is kept
  // from the first paint so nothing below moves (CLS).
  return (
    <div className={props.price ? "min-h-[15rem] sm:min-h-[12.5rem]" : ""}>
      <PricingCtaInner {...props} />
    </div>
  );
}

function PricingCtaInner({
  testModeGate = false,
  price = null,
}: {
  testModeGate?: boolean;
  price?: DisclosurePrice | null;
}) {
  const { isPending, signedIn, emailVerified, email, billing } = useBilling();
  if (isPending) return <span aria-hidden className="block h-10 w-48" />;
  // While Stripe is in test mode only allow-listed accounts may subscribe (owner decision).
  if (!signedIn && testModeGate) return <ComingSoon />;
  if (!signedIn) {
    return (
      <div className="flex flex-col items-start gap-2.5">
        <CheckoutDisclosure price={price} trial />
        <Link href="/signin?next=%2Fpricing" className={linkBtn}>
          Start 7-day free trial
        </Link>
        <AgreeLine trial />
      </div>
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
  if (!price) return <CheckoutDisclosure price={null} trial={billing.trialEligible} />;
  return (
    <div className="flex flex-col items-start gap-2.5">
      <CheckoutDisclosure price={price} trial={billing.trialEligible} />
      <CheckoutButton label={billing.trialEligible ? "Start 7-day free trial" : "Subscribe"} />
      <AgreeLine trial={billing.trialEligible} />
    </div>
  );
}

function ComingSoon() {
  return (
    <span className="inline-flex min-h-10 items-center self-start rounded-[10px] bg-[#E7EAE6] px-4 text-sm font-semibold text-muted">
      Premium is coming soon
    </span>
  );
}
