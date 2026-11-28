"use client";

import Link from "next/link";

import { useNow } from "@/lib/hooks";
import { renewalDisclosure, type DisclosurePrice } from "@/lib/billing/disclosure";
import { TRIAL_DAYS } from "@/lib/billing/entitlement";

/**
 * The renewal terms, in full and visible, right next to a button that starts Stripe Checkout
 * (ROSCA / Florida automatic renewal). The charge date is computed in the viewer's browser for
 * their time zone, so it is rendered after mount (a same-size line until then: no layout shift).
 */
export function CheckoutDisclosure({ price, trial }: { price: DisclosurePrice | null; trial: boolean }) {
  const now = useNow(60_000);
  if (!price) {
    return (
      <p className="text-[13px] text-text-2" data-testid="renewal-disclosure">
        The price isn&apos;t available right now, so checkout is closed until it is.
      </p>
    );
  }
  const d = renewalDisclosure(price, { trial, trialDays: TRIAL_DAYS, now: new Date(now ?? 0) }); // the date is shown only after mount
  return (
    <p className="text-[13.5px] leading-relaxed text-ink" data-testid="renewal-disclosure">
      {trial ? (
        <>
          {TRIAL_DAYS}-day free trial, then <strong>{d.price}</strong>, renewing automatically each{" "}
          {price.interval} until you cancel. Your card is charged on{" "}
          <strong suppressHydrationWarning>{now === null ? " " : d.chargeDate}</strong> unless you
          cancel before then. Cancel anytime in Account → Manage billing.
        </>
      ) : (
        <>
          <strong>{d.price}</strong>, renewing automatically each {price.interval} until you cancel.
          Your card is charged today and then at the start of each {price.interval}. Cancel anytime in
          Account → Manage billing.
        </>
      )}
    </p>
  );
} // prettier-ignore

/** Under the button (owner's text). */
export function AgreeLine({ trial }: { trial: boolean }) {
  return (
    <p className="text-[12.5px] text-muted-2" data-testid="agree-line">
      By {trial ? "starting your trial" : "subscribing"} you agree to the{" "}
      <Link href="/terms">Terms</Link> and the <Link href="/refund">Refund &amp; Cancellation Policy</Link>.
    </p>
  );
} // prettier-ignore
