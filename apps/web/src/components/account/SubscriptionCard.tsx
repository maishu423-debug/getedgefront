import { AgreeLine, CheckoutDisclosure } from "@/components/billing/CheckoutDisclosure";
import { COVERAGE } from "@/lib/coverage";
import type { ReactNode } from "react";

import {
  CheckoutButton,
  ManageBillingButton,
  VerifyEmailPrompt,
} from "@/components/billing/BillingButtons";
import { LocalDay } from "@/components/billing/LocalDay";
import type { AccountBilling } from "@/lib/billing/account";
import { formatMoney } from "@/lib/billing/format";

/**
 * Subscription card, the five states of design/v2/Account (v2 Phase 8 B6): trialing, active,
 * past_due, canceled (Premium until …), free. Amounts and dates come from our Stripe mirror,
 * the Stripe Price and (card, amount due) a live Stripe read — never invented: anything Stripe
 * didn't give us is left out rather than guessed.
 */
export function SubscriptionCard({
  billing,
  email,
  emailVerified,
}: {
  billing: AccountBilling;
  email: string;
  emailVerified: boolean;
}) {
  const { entitlement: e, price, card } = billing;
  const s = e.subscription;
  const amount = price ? formatMoney(price.unitAmount, price.currency) : null;
  const plan = price
    ? `Premium · ${formatMoney(price.unitAmount, price.currency, true)} / ${price.interval}`
    : "Premium";
  const cardText = card ? `${card.brand} •••• ${card.last4}` : "On file with Stripe";
  // The next charge: Stripe's own preview (tax included) when we have it, else the price
  // "plus any applicable tax" -- never a total we haven't been given.
  const nc = billing.nextCharge;
  const charge = nc
    ? nc.tax > 0
      ? `${formatMoney(nc.total, nc.currency)} (${formatMoney(nc.subtotal, nc.currency)} + ${formatMoney(nc.tax, nc.currency)} tax)`
      : formatMoney(nc.total, nc.currency)
    : amount
      ? `${amount} plus any applicable tax`
      : null;
  const day = (d: Date | null | undefined) => (d ? <LocalDay iso={d.toISOString()} /> : null);
  const manageNote =
    "Opens our secure payment page (Stripe) to update your card, see invoices or cancel.";

  let view: {
    badge: string;
    badgeCls: string;
    headline: ReactNode;
    detail: ReactNode;
    warn?: ReactNode;
    facts: [string, ReactNode][];
    action: ReactNode;
    note?: ReactNode;
  };

  if (e.state === "trialing") {
    view = {
      badge: "FREE TRIAL",
      badgeCls: "bg-[#E6F2F1] text-[#064F4B]",
      headline: "Premium · free trial",
      detail: (
        <>
          Trial ends {day(s?.trialEnd)}. You&apos;ll be charged{" "}
          {price
            ? `${formatMoney(price.unitAmount, price.currency, true)}${price.taxBehavior === "inclusive" ? "" : " + tax"}`
            : "the Premium price"}{" "}
          on {day(s?.trialEnd)} unless you cancel.
          {card ? ` (Card ending ${card.last4}.)` : ""}
        </>
      ),
      facts: [
        ["Plan", plan],
        ["Trial ends", day(s?.trialEnd)],
        ["Card", cardText],
      ],
      action: <ManageBillingButton />,
      note: manageNote,
    };
  } else if (e.state === "active") {
    view = {
      badge: "ACTIVE",
      badgeCls: "bg-[#E3F3EA] text-[#145F38]",
      headline: "Premium",
      detail: (
        <>
          Renews on {day(s?.currentPeriodEnd)}
          {charge ? ` for ${charge}` : ""}.
        </>
      ),
      facts: [
        ["Plan", plan],
        ["Next payment", day(s?.currentPeriodEnd)],
        ["Card", cardText],
      ],
      action: <ManageBillingButton />,
      note: manageNote,
    };
  } else if (e.state === "past_due") {
    const due = billing.amountDue
      ? formatMoney(billing.amountDue.amount, billing.amountDue.currency)
      : amount;
    view = {
      badge: "PAYMENT FAILED",
      badgeCls: "bg-[#FDECEA] text-[#8E1F14]",
      headline: "Premium · payment problem",
      detail: (
        <>
          We couldn&apos;t charge your card
          {billing.failedAt ? <> on {day(billing.failedAt)}</> : null}. We&apos;ll retry
          automatically
          {billing.nextAttempt ? (
            <>, next on {day(billing.nextAttempt)}</>
          ) : (
            " over the next few days"
          )}
          .
        </>
      ),
      warn: "Update your card to keep Premium. If payment keeps failing, your account moves to Free.",
      facts: [
        ["Plan", plan],
        ["Amount due", due ?? "—"],
        ["Card", cardText],
      ],
      action: <ManageBillingButton label="Update card" />,
      note: "Update your card on our secure payment page (Stripe).",
    };
  } else if (e.state === "canceling") {
    const until = e.premiumUntil;
    const trial = s?.status === "trialing";
    view = {
      badge: "CANCELLED",
      badgeCls: "bg-[#FFF1E2] text-[#8A4100]",
      headline: <>Premium until {day(until)}</>,
      detail: trial
        ? "You cancelled. You keep Premium until your trial ends, then your account moves to Free. You won't be charged."
        : "You cancelled. You keep Premium until the end of the period you paid for, then your account moves to Free.",
      facts: [
        ["Plan", plan],
        ["Premium ends", day(until)],
        ["Card", cardText],
      ],
      action: <ManageBillingButton label="Resume or manage" />,
      note: <>Changed your mind? You can resume from the payment page before {day(until)}.</>,
    };
  } else {
    const label = billing.trialEligible ? "Start 7-day free trial" : "Subscribe";
    view = {
      badge: "FREE",
      badgeCls: "bg-[#EEF1EE] text-text-2",
      headline: "Free plan",
      detail: `You have hourly METARs, daily summaries, forecasts and model guidance. Premium adds ${COVERAGE.sentence} and the live map.`,
      facts: [
        ["Plan", "Free"],
        ["Trial", billing.trialEligible ? "Available · 7 days" : "Already used"],
        // "None on file" only when we know it: a past Stripe customer may still have a card there
        ["Card", billing.hasCustomer ? "—" : "None on file"],
      ],
      action: !billing.billingEnabled ? (
        <span className="text-sm text-muted">Subscriptions aren&apos;t available right now.</span>
      ) : !billing.checkoutAllowed ? (
        <span className="text-sm font-semibold text-muted">Premium is coming soon.</span>
      ) : !emailVerified ? (
        <VerifyEmailPrompt email={email} next="/account" />
      ) : (
        <div className="flex flex-col items-start gap-2.5">
          <CheckoutDisclosure
            price={price ? { ...price, taxBehavior: price.taxBehavior ?? null } : null}
            trial={billing.trialEligible}
          />
          {price ? <CheckoutButton label={label} /> : null}
          {price ? <AgreeLine trial={billing.trialEligible} /> : null}
        </div>
      ),
      note: !billing.checkoutAllowed
        ? undefined
        : billing.trialEligible
          ? "Card required for the trial. Cancel before it ends and you won't be charged."
          : undefined,
    };
  }

  return (
    <section
      aria-labelledby="h-sub"
      data-billing-state={e.state}
      className="flex flex-col gap-4 rounded-[14px] border border-border bg-surface p-5 sm:p-6"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="h-sub" className="font-display text-xl font-semibold">
          Subscription
        </h2>
        <span
          className={`rounded-full px-2.5 py-[5px] text-[11px] font-semibold tracking-[.06em] ${view.badgeCls}`}
        >
          {view.badge}
        </span>
      </div>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex max-w-[520px] flex-col gap-1">
          <span className="font-semibold">{view.headline}</span>
          <span className="text-sm text-text-2">{view.detail}</span>
          {view.warn ? (
            <span
              role="alert"
              className="mt-2 rounded-[10px] border border-[#F3C7C2] bg-[#FDECEA] px-3.5 py-2.5 text-sm text-[#8E1F14]"
            >
              {view.warn}
            </span>
          ) : null}
        </div>
        <div className="flex flex-col items-start gap-1.5">
          {view.action}
          {view.note ? (
            <span className="max-w-[260px] text-[12.5px] text-muted-2">{view.note}</span>
          ) : null}
        </div>
      </div>
      <dl className="grid gap-x-6 gap-y-2 border-t border-hairline pt-4 text-sm sm:grid-cols-3">
        {view.facts.map(([k, v]) => (
          <div key={k} className="flex flex-col gap-0.5">
            <dt className="text-[12px] font-semibold tracking-[.04em] text-muted-2 uppercase">
              {k}
            </dt>
            <dd>{v ?? "—"}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
