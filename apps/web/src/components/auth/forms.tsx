"use client";

import Link from "next/link";
import { forwardRef, useId, useState } from "react";

/** Form pieces for the auth pages (v2 Phase 7 B, design/v2/SignIn): labelled inputs, errors
 * linked with aria-describedby, a show/hide toggle for passwords. */

export const inputCls =
  "h-[46px] w-full rounded-[10px] border border-[#CFD5D1] bg-surface px-3.5 text-[15px] text-ink placeholder:text-muted-2 focus-visible:border-brand focus-visible:ring-2 focus-visible:ring-brand/30 focus-visible:outline-none aria-[invalid=true]:border-[#B3261E]";

export const primaryBtn =
  "inline-flex min-h-[46px] w-full cursor-pointer items-center justify-center gap-2.5 rounded-[10px] bg-brand px-5 text-[15px] font-semibold text-white hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-60 focus-visible:ring-2 focus-visible:ring-brand/50 focus-visible:ring-offset-2 focus-visible:outline-none";

export const ghostBtn =
  "inline-flex min-h-[46px] cursor-pointer items-center justify-center gap-2.5 rounded-[10px] border border-[#CFD5D1] bg-surface px-5 text-[15px] font-semibold text-ink hover:bg-[#F7F8F6] disabled:cursor-not-allowed disabled:opacity-60 focus-visible:ring-2 focus-visible:ring-brand/50 focus-visible:outline-none";

type FieldProps = React.InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  error?: string | null;
  hint?: React.ReactNode;
  labelExtra?: React.ReactNode;
};

export const Field = forwardRef<HTMLInputElement, FieldProps>(function Field(
  { label, error, hint, labelExtra, id, ...rest },
  ref,
) {
  const auto = useId();
  const fid = id ?? auto;
  const errId = `${fid}-error`;
  const hintId = `${fid}-hint`;
  const describedBy = [error ? errId : null, hint ? hintId : null].filter(Boolean).join(" ");
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between gap-3">
        <label htmlFor={fid} className="text-[13px] font-semibold text-text-2">
          {label}
        </label>
        {labelExtra}
      </div>
      <input
        ref={ref}
        id={fid}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy || undefined}
        className={inputCls}
        {...rest}
      />
      {hint ? (
        <span id={hintId} className="text-[12.5px] text-muted-2">
          {hint}
        </span>
      ) : null}
      {error ? (
        <span id={errId} className="text-[13px] font-medium text-[#B3261E]">
          {error}
        </span>
      ) : null}
    </div>
  );
});

export const PasswordField = forwardRef<HTMLInputElement, Omit<FieldProps, "type">>(
  function PasswordField({ label, error, hint, labelExtra, id, ...rest }, ref) {
    const auto = useId();
    const fid = id ?? auto;
    const [show, setShow] = useState(false);
    const errId = `${fid}-error`;
    const hintId = `${fid}-hint`;
    const describedBy = [error ? errId : null, hint ? hintId : null].filter(Boolean).join(" ");
    return (
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-between gap-3">
          <label htmlFor={fid} className="text-[13px] font-semibold text-text-2">
            {label}
          </label>
          {labelExtra}
        </div>
        <div className="relative">
          <input
            ref={ref}
            id={fid}
            type={show ? "text" : "password"}
            aria-invalid={error ? true : undefined}
            aria-describedby={describedBy || undefined}
            className={`${inputCls} pr-[76px]`}
            {...rest}
          />
          <button
            type="button"
            onClick={() => setShow((s) => !s)}
            aria-pressed={show}
            aria-controls={fid}
            className="absolute top-1/2 right-1.5 min-h-9 -translate-y-1/2 cursor-pointer rounded-[7px] px-2.5 text-[13px] font-semibold text-brand hover:bg-[#F2F4F1] focus-visible:ring-2 focus-visible:ring-brand/50 focus-visible:outline-none"
          >
            {show ? "Hide" : "Show"}
            <span className="sr-only"> password</span>
          </button>
        </div>
        {hint ? (
          <span id={hintId} className="text-[12.5px] text-muted-2">
            {hint}
          </span>
        ) : null}
        {error ? (
          <span id={errId} className="text-[13px] font-medium text-[#B3261E]">
            {error}
          </span>
        ) : null}
      </div>
    );
  },
);

/** A message for the whole form (not tied to one field), announced politely. */
export function FormMessage({
  tone,
  children,
}: {
  tone: "error" | "info" | "success";
  children: React.ReactNode;
}) {
  const cls =
    tone === "error"
      ? "border-[#F3C7C2] bg-[#FDECEA] text-[#8E1F14]"
      : tone === "success"
        ? "border-[#BFE3CF] bg-[#E3F3EA] text-[#145F38]"
        : "border-border bg-[#F7F8F6] text-text-2";
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={`rounded-[10px] border px-3.5 py-3 text-sm ${cls}`}
    >
      {children}
    </div>
  );
}

export function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M45.1 24.5c0-1.6-.1-3.1-.4-4.5H24v8.5h11.8c-.5 2.8-2.1 5.1-4.4 6.7v5.5h7.1c4.2-3.8 6.6-9.5 6.6-16.2z"
      />
      <path
        fill="#34A853"
        d="M24 46c5.9 0 10.9-2 14.5-5.3l-7.1-5.5c-2 1.3-4.5 2.1-7.4 2.1-5.7 0-10.5-3.8-12.2-9H4.5v5.7C8.1 41.1 15.5 46 24 46z"
      />
      <path
        fill="#FBBC05"
        d="M11.8 28.3c-.4-1.3-.7-2.8-.7-4.3s.3-3 .7-4.3V14H4.5C3 17 2.2 20.4 2.2 24s.8 7 2.3 10l7.3-5.7z"
      />
      <path
        fill="#EA4335"
        d="M24 10.8c3.2 0 6.1 1.1 8.4 3.3l6.3-6.3C34.9 4.2 29.9 2 24 2 15.5 2 8.1 6.9 4.5 14l7.3 5.7c1.7-5.2 6.5-8.9 12.2-8.9z"
      />
    </svg>
  );
}

/** Centered card shell used by every auth page. */
export function AuthShell({ children }: { children: React.ReactNode }) {
  return (
    <main id="main" className="mx-auto flex w-full max-w-[460px] flex-col gap-5 px-4 pt-10 pb-16">
      <div className="flex flex-col gap-5 rounded-[16px] border border-border bg-surface p-6 sm:p-8">
        {children}
      </div>
      <p className="text-center text-sm text-muted-2">
        Just browsing? <Link href="/">Free data needs no account.</Link>
      </p>
    </main>
  );
}
