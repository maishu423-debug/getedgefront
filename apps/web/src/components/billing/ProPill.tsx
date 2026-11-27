"use client";

import { useBilling } from "@/lib/billing/client";

import { LockIcon } from "../LockIcon";

/**
 * The PRO pill on "Map" (v2 Phase 8 B5): shown to everyone except Premium members. It keeps its
 * space while the session loads and for Premium (invisible, not removed), so the header never
 * shifts. The map itself stays a teaser until Phase 10.
 */
export function ProPill() {
  const { isPending, billing } = useBilling();
  const hidden = isPending || billing.tier === "premium";
  return (
    <span
      aria-hidden={hidden || undefined}
      data-testid="pro-pill"
      className={`inline-flex items-center gap-1 rounded-full bg-premium-bg px-[7px] py-[3px] text-[10px] font-semibold tracking-[.05em] text-premium-text ${hidden ? "invisible" : ""}`}
    >
      <LockIcon />
      PRO
    </span>
  );
}
