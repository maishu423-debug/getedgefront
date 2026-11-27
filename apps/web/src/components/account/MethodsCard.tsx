"use client";

import { useState } from "react";

import { setPasswordAction } from "@/app/account/actions";
import { FormMessage, GoogleIcon, PasswordField } from "@/components/auth/forms";
import { authErrorMessage } from "@/components/auth/SignInForm";
import { authClient, linkGoogle } from "@/lib/auth/client";
import { PASSWORD_MESSAGES, PASSWORD_MIN, passwordProblem } from "@/lib/auth/password";

import { cardCls, darkBtn, smallBtn } from "./ProfileForm";

/**
 * Sign-in methods: connect/disconnect Google, set or change the password. The last remaining
 * method can't be removed (checked here and enforced again by Better Auth). Changing the password
 * signs out every other session.
 */
export function MethodsCard({
  googleEnabled,
  google,
  password,
  email,
}: {
  googleEnabled: boolean;
  google: { id: string } | null;
  password: { updatedAt: string } | null;
  email: string;
}) {
  const [msg, setMsg] = useState<{ tone: "error" | "success"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [pwOpen, setPwOpen] = useState(false);
  const onlyGoogle = Boolean(google) && !password;

  return (
    <section aria-labelledby="h-methods" className={cardCls}>
      <h2 id="h-methods" className="font-display text-xl font-semibold">
        Sign-in methods
      </h2>
      {msg ? <FormMessage tone={msg.tone}>{msg.text}</FormMessage> : null}
      <ul className="flex flex-col divide-y divide-hairline rounded-[10px] border border-border">
        {googleEnabled || google ? (
          <li className="flex flex-wrap items-center justify-between gap-3 px-4 py-3.5">
            <div className="flex items-center gap-3">
              <GoogleIcon />
              <div className="flex flex-col">
                <span className="font-semibold">Google</span>
                <span className="text-[13px] text-muted">
                  {google ? `Connected as ${email}` : "Not connected"}
                </span>
              </div>
            </div>
            {google ? (
              <button
                type="button"
                className={smallBtn}
                disabled={busy || onlyGoogle}
                aria-describedby={onlyGoogle ? "google-last" : undefined}
                onClick={async () => {
                  setBusy(true);
                  const { error } = await authClient.unlinkAccount({ accountId: google.id });
                  setBusy(false);
                  if (error)
                    setMsg({ tone: "error", text: authErrorMessage(error.code, error.status) });
                  else window.location.reload();
                }}
              >
                Disconnect
              </button>
            ) : (
              <button
                type="button"
                className={smallBtn}
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  const { error } = await linkGoogle("/account");
                  if (error) {
                    setBusy(false);
                    setMsg({ tone: "error", text: authErrorMessage(error.code, error.status) });
                  }
                }}
              >
                Connect Google
              </button>
            )}
            {onlyGoogle ? (
              <span id="google-last" className="w-full text-[12.5px] text-muted-2">
                Google is your only way to sign in. Set a password first if you want to disconnect
                it.
              </span>
            ) : null}
          </li>
        ) : null}
        <li className="flex flex-col gap-3 px-4 py-3.5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-col">
              <span className="font-semibold">Email and password</span>
              <span className="text-[13px] text-muted">
                {password
                  ? `Password last changed ${new Date(password.updatedAt).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}`
                  : "No password set"}
              </span>
            </div>
            <button
              type="button"
              className={smallBtn}
              aria-expanded={pwOpen}
              aria-controls="pw-form"
              onClick={() => setPwOpen((o) => !o)}
            >
              {password ? "Change password" : "Set a password"}
            </button>
          </div>
          {pwOpen ? (
            <PasswordForm
              hasPassword={Boolean(password)}
              onDone={(text) => {
                setPwOpen(false);
                setMsg({ tone: "success", text });
              }}
            />
          ) : null}
        </li>
      </ul>
    </section>
  );
}

function PasswordForm({
  hasPassword,
  onDone,
}: {
  hasPassword: boolean;
  onDone: (msg: string) => void;
}) {
  const [errors, setErrors] = useState<{ current?: string; next?: string; form?: string }>({});
  const [busy, setBusy] = useState(false);
  return (
    <form
      id="pw-form"
      noValidate
      className="flex flex-col gap-3 sm:max-w-[420px]"
      onSubmit={async (e) => {
        e.preventDefault();
        const fd = new FormData(e.currentTarget);
        const current = String(fd.get("current") ?? "");
        const next = String(fd.get("new") ?? "");
        const errs: typeof errors = {};
        if (hasPassword && !current) errs.current = "Enter your current password.";
        const p = passwordProblem(next);
        if (p) errs.next = PASSWORD_MESSAGES[p];
        setErrors(errs);
        if (Object.keys(errs).length) return;
        setBusy(true);
        if (hasPassword) {
          const { error } = await authClient.changePassword({
            currentPassword: current,
            newPassword: next,
            revokeOtherSessions: true,
          });
          setBusy(false);
          if (error) {
            if (error.code === "PASSWORD_TOO_COMMON")
              setErrors({ next: PASSWORD_MESSAGES.too_common });
            else if (error.code === "INVALID_PASSWORD")
              setErrors({ current: "That is not your current password." });
            else setErrors({ form: authErrorMessage(error.code, error.status) });
            return;
          }
          onDone("Password changed. You were signed out on your other devices.");
        } else {
          const res = await setPasswordAction(next);
          setBusy(false);
          if (!res.ok) return setErrors({ next: res.error });
          onDone("Password set. You can now sign in with your email and password too.");
          window.location.reload();
        }
      }}
    >
      {errors.form ? <FormMessage tone="error">{errors.form}</FormMessage> : null}
      {hasPassword ? (
        <PasswordField
          label="Current password"
          name="current"
          autoComplete="current-password"
          error={errors.current}
        />
      ) : null}
      <PasswordField
        label="New password"
        name="new"
        autoComplete="new-password"
        hint={`At least ${PASSWORD_MIN} characters. Avoid common passwords.`}
        error={errors.next}
      />
      <div>
        <button type="submit" className={darkBtn} disabled={busy}>
          {busy ? "Saving…" : hasPassword ? "Change password" : "Set password"}
        </button>
      </div>
    </form>
  );
}
