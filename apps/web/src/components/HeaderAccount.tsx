"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { authClient, reloadTo } from "@/lib/auth/client";

/**
 * Header account slot (v2 Phase 7 B). Pages are prerendered and the same for everyone, so the
 * session is read in the browser. The slot has a fixed size from the first paint (a blank
 * placeholder while the session loads), so there is no layout shift and no "Sign in → avatar"
 * flash. Signed out: Sign in + Start free trial. Signed in: FREE badge + avatar menu.
 */
export function HeaderAccount() {
  const { data, isPending } = authClient.useSession();
  return (
    <div
      className="flex h-10 w-[228px] items-center justify-end gap-1.5"
      data-testid="header-account"
    >
      {isPending ? (
        <span aria-hidden className="h-10 w-full" />
      ) : data?.user ? (
        <SignedIn name={data.user.name || data.user.email} />
      ) : (
        <>
          <Link
            href="/signin"
            className="inline-flex min-h-10 items-center rounded-[8px] px-3 text-sm font-semibold text-ink no-underline hover:text-ink"
          >
            Sign in
          </Link>
          <Link
            href="/pricing"
            className="inline-flex min-h-10 items-center rounded-[10px] bg-brand px-4 text-sm font-semibold whitespace-nowrap text-white no-underline hover:bg-brand-hover hover:text-white"
          >
            Start free trial
          </Link>
        </>
      )}
    </div>
  );
}

export function initials(name: string): string {
  const parts = name
    .replace(/@.*/, "")
    .split(/[\s._-]+/)
    .filter(Boolean);
  const first = parts[0]?.[0] ?? "?";
  const second = parts.length > 1 ? parts[parts.length - 1]![0] : "";
  return (first + (second ?? "")).toUpperCase();
}

function SignedIn({ name }: { name: string }) {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (
        !menu.current?.contains(e.target as Node) &&
        !button.current?.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        button.current?.focus();
      }
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    menu.current?.querySelector<HTMLElement>("a,button")?.focus();
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="relative flex items-center gap-1.5">
      <span className="rounded-full bg-[#EEF1EE] px-2.5 py-[5px] text-[11px] font-semibold tracking-[.05em] text-text-2">
        FREE
      </span>
      <button
        ref={button}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Account menu for ${name}`}
        onClick={() => setOpen((o) => !o)}
        className="inline-flex size-10 cursor-pointer items-center justify-center rounded-full bg-ink text-sm font-semibold text-white focus-visible:ring-2 focus-visible:ring-brand/50 focus-visible:outline-none"
      >
        {initials(name)}
      </button>
      {open ? (
        <div
          ref={menu}
          role="menu"
          aria-label="Account"
          className="absolute top-12 right-0 z-30 flex w-48 flex-col rounded-[10px] border border-border bg-surface p-1.5 shadow-[0_8px_24px_rgba(16,26,28,.12)]"
        >
          <Link
            role="menuitem"
            href="/account"
            onClick={() => setOpen(false)}
            className="rounded-[7px] px-3 py-2.5 text-sm text-ink no-underline hover:bg-[#F2F4F1] hover:text-ink"
          >
            Account
          </Link>
          <button
            role="menuitem"
            type="button"
            onClick={async () => {
              await authClient.signOut();
              reloadTo("/");
            }}
            className="cursor-pointer rounded-[7px] px-3 py-2.5 text-left text-sm text-ink hover:bg-[#F2F4F1]"
          >
            Sign out
          </button>
        </div>
      ) : null}
    </div>
  );
}
