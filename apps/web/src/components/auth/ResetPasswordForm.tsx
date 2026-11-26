"use client";

import Link from "next/link";
import { useRef, useState } from "react";

import { authClient, reloadTo } from "@/lib/auth/client";
import { PASSWORD_MESSAGES, PASSWORD_MIN, passwordProblem } from "@/lib/auth/password";

import { Field, FormMessage, PasswordField, primaryBtn } from "./forms";
import { authErrorMessage } from "./SignInForm";

/**
 * /reset-password: without a token, ask for the email (the answer is the same whether or not an
 * account exists); with ?token= (from the email link), set the new password. Resetting signs out
 * every other session (Better Auth: revokeSessionsOnPasswordReset).
 */
export function ResetPasswordForm({
  token,
  linkError,
}: {
  token: string | null;
  linkError: string | null;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(linkError ? authErrorMessage(linkError) : null);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const ref = useRef<HTMLFormElement>(null);
  const focusError = () =>
    requestAnimationFrame(() =>
      ref.current?.querySelector<HTMLElement>("[aria-invalid=true], [role=alert]")?.focus(),
    );

  if (!token) {
    return (
      <>
        <div className="flex flex-col gap-1.5">
          <h1 className="font-display text-[26px] font-bold tracking-[-0.02em]">
            Reset your password
          </h1>
          <p className="text-sm text-muted">
            Enter the email you signed up with. If an account exists, we&apos;ll send a reset link
            that works for 1 hour.
          </p>
        </div>
        <form
          ref={ref}
          noValidate
          className="flex flex-col gap-4"
          onSubmit={async (e) => {
            e.preventDefault();
            const email = String(new FormData(e.currentTarget).get("email") ?? "").trim();
            if (!/^\S+@\S+\.\S+$/.test(email)) {
              setFieldError("Enter a valid email address.");
              return focusError();
            }
            setFieldError(null);
            setBusy(true);
            const { error: err } = await authClient.requestPasswordReset({
              email,
              redirectTo: "/reset-password",
            });
            setBusy(false);
            if (err && err.status === 429) {
              setError(authErrorMessage(err.code, err.status));
              return focusError();
            }
            reloadTo("/check-email?kind=reset");
          }}
        >
          {error ? (
            <div tabIndex={-1}>
              <FormMessage tone="error">{error}</FormMessage>
            </div>
          ) : null}
          <Field
            label="Email"
            name="email"
            type="email"
            autoComplete="email"
            error={fieldError}
            required
          />
          <button type="submit" className={primaryBtn} disabled={busy}>
            {busy ? "Please wait…" : "Send reset link"}
          </button>
        </form>
        <Link href="/signin" className="text-sm font-semibold">
          Back to sign in
        </Link>
      </>
    );
  }

  return (
    <>
      <div className="flex flex-col gap-1.5">
        <h1 className="font-display text-[26px] font-bold tracking-[-0.02em]">
          Choose a new password
        </h1>
        <p className="text-sm text-muted">You&apos;ll be signed out on your other devices.</p>
      </div>
      <form
        ref={ref}
        noValidate
        className="flex flex-col gap-4"
        onSubmit={async (e) => {
          e.preventDefault();
          const pw = String(new FormData(e.currentTarget).get("password") ?? "");
          const p = passwordProblem(pw);
          if (p) {
            setFieldError(PASSWORD_MESSAGES[p]);
            return focusError();
          }
          setFieldError(null);
          setBusy(true);
          const { error: err } = await authClient.resetPassword({ newPassword: pw, token });
          setBusy(false);
          if (err) {
            if (err.code === "PASSWORD_TOO_COMMON") setFieldError(PASSWORD_MESSAGES.too_common);
            else setError(authErrorMessage(err.code, err.status));
            return focusError();
          }
          reloadTo("/signin?reset=1");
        }}
      >
        {error ? (
          <div tabIndex={-1}>
            <FormMessage tone="error">{error}</FormMessage>
          </div>
        ) : null}
        <PasswordField
          label="New password"
          name="password"
          autoComplete="new-password"
          hint={`At least ${PASSWORD_MIN} characters. Avoid common passwords.`}
          error={fieldError}
          required
        />
        <button type="submit" className={primaryBtn} disabled={busy}>
          {busy ? "Please wait…" : "Save new password"}
        </button>
      </form>
    </>
  );
}
