"use client";

import Link from "next/link";
import { useRef, useState } from "react";

import { authClient, reloadTo, signInWithGoogle } from "@/lib/auth/client";
import { PASSWORD_MESSAGES, PASSWORD_MIN, passwordProblem } from "@/lib/auth/password";

import { Field, FormMessage, GoogleIcon, ghostBtn, PasswordField, primaryBtn } from "./forms";

type Mode = "signin" | "signup";

/** Plain-language messages for Better Auth's error codes. Never says whether an email exists. */
export function authErrorMessage(code: string | undefined, status?: number): string {
  if (status === 429 || code === "TOO_MANY_REQUESTS")
    return "Too many attempts. Please wait a few minutes and try again.";
  switch (code) {
    case "INVALID_EMAIL_OR_PASSWORD":
    case "INVALID_PASSWORD":
    case "CREDENTIAL_ACCOUNT_NOT_FOUND":
      return "The email or password is not right.";
    case "PASSWORD_TOO_COMMON":
      return PASSWORD_MESSAGES.too_common;
    case "PASSWORD_TOO_SHORT":
      return PASSWORD_MESSAGES.too_short;
    case "PASSWORD_TOO_LONG":
      return PASSWORD_MESSAGES.too_long;
    case "INVALID_EMAIL":
      return "Enter a valid email address.";
    case "account_not_linked":
    case "ACCOUNT_NOT_LINKED":
      return "There is already an EdgeFront account with this email. Sign in with your email and password, confirm your email, then connect Google from your account page.";
    case "INVALID_TOKEN":
      return "This link is invalid or has expired. Request a new one.";
    default:
      return "Something went wrong. Please try again.";
  }
}

export function SignInForm({
  next,
  googleEnabled,
  initialMode = "signin",
  initialError,
  notice,
}: {
  next: string;
  googleEnabled: boolean;
  initialMode?: Mode;
  initialError?: string | null;
  notice?: string | null;
}) {
  const [mode, setMode] = useState<Mode>(initialMode);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(
    initialError ? authErrorMessage(initialError) : null,
  );
  const [fieldErrors, setFieldErrors] = useState<{
    name?: string;
    email?: string;
    password?: string;
  }>({});
  const formRef = useRef<HTMLFormElement>(null);
  const up = mode === "signup";

  const focusFirstError = () =>
    requestAnimationFrame(() =>
      formRef.current?.querySelector<HTMLElement>("[aria-invalid=true], [role=alert]")?.focus(),
    );

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const name = String(fd.get("name") ?? "").trim();
    const email = String(fd.get("email") ?? "").trim();
    const password = String(fd.get("password") ?? "");
    const errs: typeof fieldErrors = {};
    if (up && !name) errs.name = "Enter your name.";
    if (!/^\S+@\S+\.\S+$/.test(email)) errs.email = "Enter a valid email address.";
    if (up) {
      const p = passwordProblem(password);
      if (p) errs.password = PASSWORD_MESSAGES[p];
    } else if (!password) errs.password = "Enter your password.";
    setFieldErrors(errs);
    setFormError(null);
    if (Object.keys(errs).length) return focusFirstError();

    setBusy(true);
    try {
      if (up) {
        const { error } = await authClient.signUp.email({
          name,
          email,
          password,
          callbackURL: `/verify-email?next=${encodeURIComponent(next)}`,
        });
        if (error) {
          setFormError(authErrorMessage(error.code, error.status));
          return focusFirstError();
        }
        reloadTo(`/check-email?kind=verify&next=${encodeURIComponent(next)}`);
      } else {
        const { error } = await authClient.signIn.email({ email, password });
        if (error) {
          setFormError(authErrorMessage(error.code, error.status));
          return focusFirstError();
        }
        reloadTo(next);
      }
    } finally {
      setBusy(false);
    }
  }

  const tab = (key: Mode, label: string) => (
    <button
      key={key}
      type="button"
      role="tab"
      id={`tab-${key}`}
      aria-selected={mode === key}
      aria-controls="auth-panel"
      onClick={() => {
        setMode(key);
        setFormError(null);
        setFieldErrors({});
      }}
      className={`min-h-10 flex-1 cursor-pointer rounded-[7px] px-3 text-[13px] font-medium ${
        mode === key
          ? "bg-surface text-ink shadow-[0_1px_2px_rgba(16,26,28,.14)]"
          : "text-muted hover:text-ink"
      }`}
    >
      {label}
    </button>
  );

  return (
    <>
      <div role="tablist" aria-label="Account" className="flex rounded-[9px] bg-[#E7EAE6] p-[3px]">
        {tab("signin", "Sign in")}
        {tab("signup", "Create account")}
      </div>
      <div
        id="auth-panel"
        role="tabpanel"
        aria-labelledby={`tab-${mode}`}
        className="flex flex-col gap-5"
      >
        <div className="flex flex-col gap-1.5">
          <h1 className="font-display text-[26px] font-bold tracking-[-0.02em]">
            {up ? "Create your account" : "Welcome back"}
          </h1>
          <p className="text-sm text-muted">
            {up
              ? "Start with a 7-day free trial of Premium after you sign up."
              : "Sign in to see 5-minute data and the live map."}
          </p>
        </div>

        {googleEnabled ? (
          <>
            <button
              type="button"
              className={`${ghostBtn} w-full`}
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                const errorURL = `/signin?next=${encodeURIComponent(next)}`;
                const { error } = await signInWithGoogle(next, errorURL);
                if (error) {
                  setBusy(false);
                  setFormError(authErrorMessage(error.code, error.status));
                }
              }}
            >
              <GoogleIcon />
              Continue with Google
            </button>
            <div className="flex items-center gap-3 text-[12.5px] text-muted-2">
              <span className="h-px flex-1 bg-border" />
              or with email
              <span className="h-px flex-1 bg-border" />
            </div>
          </>
        ) : null}

        <form ref={formRef} noValidate onSubmit={onSubmit} className="flex flex-col gap-4">
          {notice && !formError ? <FormMessage tone="success">{notice}</FormMessage> : null}
          {formError ? (
            <div tabIndex={-1}>
              <FormMessage tone="error">{formError}</FormMessage>
            </div>
          ) : null}
          {up ? (
            <Field
              label="Name"
              name="name"
              type="text"
              autoComplete="name"
              error={fieldErrors.name}
              required
            />
          ) : null}
          <Field
            label="Email"
            name="email"
            type="email"
            autoComplete="email"
            inputMode="email"
            error={fieldErrors.email}
            required
          />
          <PasswordField
            label="Password"
            name="password"
            autoComplete={up ? "new-password" : "current-password"}
            placeholder={up ? `At least ${PASSWORD_MIN} characters` : undefined}
            hint={up ? `At least ${PASSWORD_MIN} characters. Avoid common passwords.` : undefined}
            error={fieldErrors.password}
            required
            labelExtra={
              up ? null : (
                <Link
                  href={`/reset-password?next=${encodeURIComponent(next)}`}
                  className="text-[13px]"
                >
                  Forgot password?
                </Link>
              )
            }
          />
          <button type="submit" className={primaryBtn} disabled={busy}>
            {busy ? "Please wait…" : up ? "Create account" : "Sign in"}
          </button>
        </form>
        {up ? (
          <p className="text-[12.5px] leading-relaxed text-muted-2">
            By creating an account you agree to the <Link href="/terms">Terms</Link> and{" "}
            <Link href="/privacy">Privacy Policy</Link>. We&apos;ll send a link to confirm your
            email.
          </p>
        ) : null}
      </div>
    </>
  );
}
