"use client";

import { useState } from "react";

import { authClient } from "@/lib/auth/client";
import {
  BILLING_ERRORS,
  openPortal,
  startCheckout,
  type BillingActionError,
} from "@/lib/billing/client";

const primary =
  "inline-flex min-h-10 cursor-pointer items-center justify-center rounded-[10px] bg-brand px-4 text-sm font-semibold text-white hover:bg-brand-hover disabled:cursor-wait disabled:opacity-70";
const secondary =
  "inline-flex min-h-10 cursor-pointer items-center justify-center rounded-[10px] border border-border bg-surface px-4 text-sm font-semibold text-ink hover:bg-[#F2F4F1] disabled:cursor-wait disabled:opacity-70";

function ErrorLine({ error }: { error: BillingActionError | null }) {
  return error ? (
    <span role="alert" className="text-[13px] text-[#8E1F14]">
      {BILLING_ERRORS[error]}
    </span>
  ) : null;
}

/** "Start 7-day free trial" / "Subscribe": server-side Checkout Session, then Stripe. */
export function CheckoutButton({ label, className = "" }: { label: string; className?: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<BillingActionError | null>(null);
  return (
    <div className="flex flex-col items-start gap-1.5">
      <button
        type="button"
        className={`${primary} ${className}`}
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setError(null);
          const e = await startCheckout();
          if (e) {
            setError(e);
            setBusy(false);
          }
        }}
      >
        {busy ? "Opening secure checkout…" : label}
      </button>
      <ErrorLine error={error} />
    </div>
  );
}

/** "Manage billing": Stripe Customer Portal (card, invoices, cancel or resume). */
export function ManageBillingButton({ label = "Manage billing" }: { label?: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<BillingActionError | null>(null);
  return (
    <div className="flex flex-col items-start gap-1.5">
      <button
        type="button"
        className={secondary}
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setError(null);
          const e = await openPortal();
          if (e) {
            setError(e);
            setBusy(false);
          }
        }}
      >
        {busy ? "Opening…" : label}
      </button>
      <ErrorLine error={error} />
    </div>
  );
}

/** Checkout needs a confirmed email: say so, and offer to resend the link. */
export function VerifyEmailPrompt({ email, next = "/pricing" }: { email: string; next?: string }) {
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle");
  return (
    <div
      role="status"
      className="flex max-w-[360px] flex-col items-start gap-2 rounded-[10px] border border-[#F2D39B] bg-[#FFF6E5] px-3.5 py-3 text-sm text-[#6B4300]"
    >
      <span>
        Confirm your email address to start the trial. We sent a link to <strong>{email}</strong>.
      </span>
      <button
        type="button"
        className="cursor-pointer text-sm font-semibold text-ink underline disabled:cursor-default disabled:no-underline"
        disabled={state !== "idle"}
        onClick={async () => {
          setState("sending");
          await authClient.sendVerificationEmail({
            email,
            callbackURL: `/verify-email?next=${encodeURIComponent(next)}`,
          });
          setState("sent");
        }}
      >
        {state === "sent"
          ? "Sent. Check your inbox."
          : state === "sending"
            ? "Sending…"
            : "Resend the link"}
      </button>
    </div>
  );
}
