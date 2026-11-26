"use client";

import { useState } from "react";

import { Field, FormMessage } from "@/components/auth/forms";
import { authErrorMessage } from "@/components/auth/SignInForm";
import { authClient } from "@/lib/auth/client";

export const cardCls =
  "flex flex-col gap-4 rounded-[14px] border border-border bg-surface p-5 sm:p-6";
export const smallBtn =
  "inline-flex min-h-10 cursor-pointer items-center rounded-[9px] border border-[#CFD5D1] bg-surface px-4 text-sm font-semibold text-ink hover:bg-[#F7F8F6] disabled:cursor-not-allowed disabled:opacity-60 focus-visible:ring-2 focus-visible:ring-brand/50 focus-visible:outline-none";
export const darkBtn =
  "inline-flex min-h-10 cursor-pointer items-center rounded-[9px] bg-ink px-4 text-sm font-semibold text-white hover:bg-[#2A3533] disabled:cursor-not-allowed disabled:opacity-60 focus-visible:ring-2 focus-visible:ring-brand/50 focus-visible:outline-none";

/** Profile: editable name; email read-only with its verified state and a resend action. */
export function ProfileForm({
  name,
  email,
  emailVerified,
}: {
  name: string;
  email: string;
  emailVerified: boolean;
}) {
  const [value, setValue] = useState(name);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: "error" | "success"; text: string } | null>(null);
  const [nameError, setNameError] = useState<string | null>(null);

  return (
    <section aria-labelledby="h-prof" className={cardCls}>
      <h2 id="h-prof" className="font-display text-xl font-semibold">
        Profile
      </h2>
      <form
        noValidate
        className="flex flex-col gap-4"
        onSubmit={async (e) => {
          e.preventDefault();
          const v = value.trim();
          if (!v) {
            setNameError("Enter your name.");
            return;
          }
          setNameError(null);
          setBusy(true);
          const { error } = await authClient.updateUser({ name: v });
          setBusy(false);
          setMsg(
            error
              ? { tone: "error", text: authErrorMessage(error.code, error.status) }
              : { tone: "success", text: "Saved." },
          );
        }}
      >
        {msg ? <FormMessage tone={msg.tone}>{msg.text}</FormMessage> : null}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="Name"
            name="name"
            autoComplete="name"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            error={nameError}
          />
          <div className="flex flex-col gap-1.5">
            <Field
              label="Email"
              name="email"
              type="email"
              value={email}
              readOnly
              aria-readonly
              hint={
                emailVerified ? (
                  <span className="font-semibold text-[#145F38]">Verified</span>
                ) : (
                  <ResendVerification email={email} />
                )
              }
            />
          </div>
        </div>
        <div>
          <button type="submit" className={darkBtn} disabled={busy || value.trim() === name}>
            {busy ? "Saving…" : "Save changes"}
          </button>
        </div>
      </form>
    </section>
  );
}

function ResendVerification({ email }: { email: string }) {
  const [state, setState] = useState<"idle" | "busy" | "sent" | "error">("idle");
  return (
    <span className="flex flex-wrap items-center gap-2">
      <span className="font-semibold text-[#8A4100]">Not verified.</span>
      {state === "sent" ? (
        <span role="status">Confirmation email sent. Check your inbox.</span>
      ) : (
        <button
          type="button"
          className="cursor-pointer font-semibold text-brand underline disabled:opacity-60"
          disabled={state === "busy"}
          onClick={async () => {
            setState("busy");
            const { error } = await authClient.sendVerificationEmail({
              email,
              callbackURL: "/verify-email?next=%2Faccount",
            });
            setState(error ? "error" : "sent");
          }}
        >
          Resend confirmation email
        </button>
      )}
      {state === "error" ? (
        <span role="alert">Could not send right now. Try again later.</span>
      ) : null}
    </span>
  );
}
