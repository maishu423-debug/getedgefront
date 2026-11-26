"use client";

import { useState } from "react";

import { FormMessage, PasswordField } from "@/components/auth/forms";
import { authErrorMessage } from "@/components/auth/SignInForm";
import { authClient, reloadTo, signInWithGoogle } from "@/lib/auth/client";

import { cardCls, smallBtn } from "./ProfileForm";

/**
 * Delete account (design/v2/Account, copy as designed — flagged for the owner's lawyer).
 * Re-authentication: a sign-in within the last 10 minutes, or the password; Google-only users
 * whose session is older sign in again. Better Auth deletes the user, its sessions and sign-in
 * methods; the server sends a notice and logs a non-identifying audit event.
 */
export function DeleteAccount({ hasPassword, fresh }: { hasPassword: boolean; fresh: boolean }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pwError, setPwError] = useState<string | null>(null);
  const needPassword = !fresh && hasPassword;
  const needReauth = !fresh && !hasPassword;

  return (
    <section aria-labelledby="h-danger" className={`${cardCls} border-[#F3C7C2]`}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex max-w-[560px] flex-col gap-1">
          <h2 id="h-danger" className="font-display text-xl font-semibold">
            Delete account
          </h2>
          <span className="text-sm text-text-2">
            Permanently deletes your account and profile. Cancel any active subscription first;
            billing records are kept by our payment processor as the law requires.
          </span>
        </div>
        {!open ? (
          <button
            type="button"
            className={`${smallBtn} border-[#B3261E] text-[#B3261E] hover:bg-[#FDECEA]`}
            onClick={() => setOpen(true)}
            aria-expanded={false}
            aria-controls="delete-confirm"
          >
            Delete account
          </button>
        ) : null}
      </div>
      {open ? (
        <form
          id="delete-confirm"
          noValidate
          className="flex flex-col gap-3 rounded-[10px] border border-[#F3C7C2] bg-[#FFF8F7] p-4"
          onSubmit={async (e) => {
            e.preventDefault();
            setError(null);
            const password = String(new FormData(e.currentTarget).get("password") ?? "");
            if (needPassword && !password) {
              setPwError("Enter your password to confirm.");
              return;
            }
            setPwError(null);
            setBusy(true);
            const { error: err } = await authClient.deleteUser(
              needPassword ? { password, callbackURL: "/" } : { callbackURL: "/" },
            );
            setBusy(false);
            if (err) {
              if (err.code === "INVALID_PASSWORD") setPwError("That password is not right.");
              else if (err.code === "SESSION_EXPIRED")
                setError("For your security, sign in again and retry.");
              else setError(authErrorMessage(err.code, err.status));
              return;
            }
            reloadTo("/?account=deleted");
          }}
        >
          <p className="text-sm font-semibold" role="note">
            This can&apos;t be undone. Your account, profile and sign-in methods will be deleted.
          </p>
          {error ? <FormMessage tone="error">{error}</FormMessage> : null}
          {needPassword ? (
            <PasswordField
              label="Your password"
              name="password"
              autoComplete="current-password"
              error={pwError}
              autoFocus
            />
          ) : null}
          {needReauth ? (
            <div className="flex flex-col gap-2">
              <p className="text-sm text-text-2">
                For your security, sign in with Google again, then delete the account.
              </p>
              <div>
                <button
                  type="button"
                  className={smallBtn}
                  onClick={() => signInWithGoogle("/account#h-danger", "/account")}
                >
                  Sign in again with Google
                </button>
              </div>
            </div>
          ) : (
            <div className="flex flex-wrap gap-2">
              <button
                type="submit"
                disabled={busy}
                className="inline-flex min-h-10 cursor-pointer items-center rounded-[9px] bg-[#B3261E] px-4 text-sm font-semibold text-white hover:bg-[#8E1F14] disabled:opacity-60"
              >
                {busy ? "Deleting…" : "Delete my account permanently"}
              </button>
              <button type="button" className={smallBtn} onClick={() => setOpen(false)}>
                Cancel
              </button>
            </div>
          )}
        </form>
      ) : null}
    </section>
  );
}
