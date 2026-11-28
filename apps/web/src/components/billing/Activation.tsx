"use client";

import { useEffect, useState } from "react";

import { reloadTo } from "@/lib/auth/client";

/**
 * After Stripe Checkout (v2 Phase 8 B3): the return to /account?checkout=success grants
 * nothing by itself. This polls our own /api/me until the webhook-mirrored subscription makes
 * the account Premium (checked every 3 s), then reloads; after 60 s it says what's going on
 * instead (v2 Phase 10 B1). Premium is never granted from the success URL alone.
 */
export function Activation({
  timeoutMs = 60_000,
  everyMs = 3_000,
}: {
  timeoutMs?: number;
  everyMs?: number;
}) {
  const [timedOut, setTimedOut] = useState(false);
  useEffect(() => {
    const started = Date.now();
    let stop = false;
    const tick = async () => {
      if (stop) return;
      try {
        const me = (await (await fetch("/api/me", { cache: "no-store" })).json()) as {
          tier?: string;
        };
        if (me.tier === "premium") {
          reloadTo("/account");
          return;
        }
      } catch {
        // keep polling
      }
      if (Date.now() - started >= timeoutMs) setTimedOut(true);
      else setTimeout(tick, everyMs);
    };
    void tick();
    return () => {
      stop = true;
    };
  }, [timeoutMs, everyMs]);

  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-start gap-3 rounded-[12px] border border-[#BFE0DD] bg-[#E6F2F1] px-4 py-3.5 text-sm text-[#064F4B]"
    >
      {timedOut ? (
        <span>This is taking longer than usual. Refresh in a minute, or contact support.</span>
      ) : (
        <>
          <span
            aria-hidden
            className="mt-1 size-3 animate-spin rounded-full border-2 border-[#064F4B] border-t-transparent"
          />
          <span>
            Activating Premium… This page updates as soon as Stripe confirms your subscription.
          </span>
        </>
      )}
    </div>
  );
}
