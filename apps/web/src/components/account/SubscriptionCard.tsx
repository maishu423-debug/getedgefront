import Link from "next/link";

/**
 * Subscription card, "free" state of design/v2/Account (Phase 7). Billing (trialing, active,
 * past_due, canceled) arrives with Stripe in Phase 8. No price is written here: it will come from
 * Stripe/config (STRIPE_PRICE_ID), never hard-coded copy.
 */
export function SubscriptionCard() {
  return (
    <section
      aria-labelledby="h-sub"
      className="flex flex-col gap-4 rounded-[14px] border border-border bg-surface p-5 sm:p-6"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="h-sub" className="font-display text-xl font-semibold">
          Subscription
        </h2>
        <span className="rounded-full bg-[#EEF1EE] px-2.5 py-[5px] text-[11px] font-semibold tracking-[.06em] text-text-2">
          FREE
        </span>
      </div>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex max-w-[520px] flex-col gap-1">
          <span className="font-semibold">Free plan</span>
          <span className="text-sm text-text-2">
            You have hourly METARs, daily summaries, forecasts and model guidance. Premium adds
            5-minute data and the live map.
          </span>
        </div>
        <div className="flex flex-col items-start gap-1.5">
          <Link
            href="/pricing"
            className="inline-flex min-h-10 items-center rounded-[10px] bg-brand px-4 text-sm font-semibold text-white no-underline hover:bg-brand-hover hover:text-white"
          >
            Start 7-day free trial
          </Link>
          <span className="max-w-[260px] text-[12.5px] text-muted-2">
            Card required for the trial. Cancel before it ends and you won&apos;t be charged.
          </span>
        </div>
      </div>
      <dl className="grid gap-x-6 gap-y-2 border-t border-hairline pt-4 text-sm sm:grid-cols-3">
        {[
          ["Plan", "Free"],
          ["Trial", "Available · 7 days"],
          ["Card", "None on file"],
        ].map(([k, v]) => (
          <div key={k} className="flex flex-col gap-0.5">
            <dt className="text-[12px] font-semibold tracking-[.04em] text-muted-2 uppercase">
              {k}
            </dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
