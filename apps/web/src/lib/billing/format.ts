/** Display helpers for billing (pure; shared by server and client components). */

/** "$20.00" (or "$20" with `short`) from Stripe's smallest-unit amount. */
export function formatMoney(amount: number, currency: string, short = false): string {
  const whole = amount % 100 === 0;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency.toUpperCase(),
    minimumFractionDigits: short && whole ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(amount / 100);
}

/** "Dec 3, 2026" in the given time zone (UTC on the server, the viewer's own in the browser). */
export function formatDay(d: Date | string, timeZone?: string): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    ...(timeZone ? { timeZone } : {}),
  }).format(typeof d === "string" ? new Date(d) : d);
}

export const CARD_BRANDS: Record<string, string> = {
  visa: "Visa",
  mastercard: "Mastercard",
  amex: "American Express",
  discover: "Discover",
  jcb: "JCB",
  diners: "Diners Club",
  unionpay: "UnionPay",
};
