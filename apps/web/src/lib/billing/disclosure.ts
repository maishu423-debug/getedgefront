/**
 * The automatic-renewal disclosure shown next to every button that leads to Stripe Checkout
 * (v2 Part 2 §4: federal ROSCA and Florida's automatic-renewal law). Pure, so the price, tax
 * wording and date are unit-tested. The price and tax behaviour come from the Stripe Price (never
 * hard-coded); the date is computed for the viewer (today + the trial length, their time zone).
 *
 * Trial (owner's text):
 *   "7-day free trial, then $20/month plus applicable tax, renewing automatically each month until
 *    you cancel. Your card is charged on December 5, 2026 unless you cancel before then. Cancel
 *    anytime in Account → Manage billing."
 */
import { formatMoney } from "./format";

export interface DisclosurePrice {
  unitAmount: number;
  currency: string;
  interval: string; // "month"
  /** Stripe Price tax_behavior: "exclusive" (tax added), "inclusive" or "unspecified" */
  taxBehavior: string | null;
}

export interface Disclosure {
  /** "$20/month plus applicable tax" */
  price: string;
  /** "December 5, 2026" (trial only) */
  chargeDate: string | null;
  /** the whole sentence, plain text (tests, accessible text) */
  text: string;
}

export function taxWording(taxBehavior: string | null): string {
  return taxBehavior === "inclusive" ? "including applicable tax" : "plus applicable tax";
}

export function chargeDate(now: Date, trialDays: number, timeZone?: string): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
    ...(timeZone ? { timeZone } : {}),
  }).format(new Date(now.getTime() + trialDays * 86_400_000));
}

export function renewalDisclosure(
  p: DisclosurePrice,
  opts: { trial: boolean; trialDays: number; now: Date; timeZone?: string },
): Disclosure {
  const price = `${formatMoney(p.unitAmount, p.currency, true)}/${p.interval} ${taxWording(p.taxBehavior)}`;
  const every = `renewing automatically each ${p.interval} until you cancel`;
  if (opts.trial) {
    const date = chargeDate(opts.now, opts.trialDays, opts.timeZone);
    return {
      price,
      chargeDate: date,
      text: `${opts.trialDays}-day free trial, then ${price}, ${every}. Your card is charged on ${date} unless you cancel before then. Cancel anytime in Account → Manage billing.`,
    };
  }
  return {
    price,
    chargeDate: null,
    text: `${price}, ${every}. Your card is charged today and then at the start of each ${p.interval}. Cancel anytime in Account → Manage billing.`,
  };
}
