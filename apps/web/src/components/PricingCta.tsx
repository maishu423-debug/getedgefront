"use client";

import Link from "next/link";

import { authClient } from "@/lib/auth/client";

/** Premium card call to action (v2 Phase 7): signed out → sign in, then back to /pricing.
 * Signed in → still "Coming soon" until billing exists (Phase 8). Fixed height, no shift. */
export function PricingCta() {
  const { data, isPending } = authClient.useSession();
  if (isPending) return <span aria-hidden className="block h-10 w-40" />;
  if (!data?.user) {
    return (
      <Link
        href="/signin?next=%2Fpricing"
        className="inline-flex min-h-10 items-center self-start rounded-[9px] bg-brand px-4 text-sm font-semibold text-white no-underline hover:bg-brand-hover hover:text-white"
      >
        Start free trial
      </Link>
    );
  }
  return (
    <button
      type="button"
      disabled
      aria-disabled
      className="inline-flex min-h-10 cursor-not-allowed items-center self-start rounded-[9px] bg-[#E7EAE6] px-4 text-sm font-semibold text-muted"
    >
      Coming soon
    </button>
  );
}
