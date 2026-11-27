"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";

import { authClient, reloadTo } from "@/lib/auth/client";

import { LockIcon } from "./LockIcon";

type Active = "stations" | "pricing" | "sources" | undefined;

const item =
  "flex min-h-12 items-center gap-2 rounded-[8px] px-3 text-base text-ink no-underline hover:bg-[#F2F4F1] hover:text-ink";

/**
 * Header menu below 640 px (v2 Phase 7 A1.2). A disclosure, not a modal: focus moves into the
 * panel when it opens, Esc closes it and returns focus to the button, choosing a link closes it,
 * and Tab can always leave it (nothing is trapped).
 */
export function MobileMenu({ active }: { active: Active }) {
  const [open, setOpen] = useState(false);
  const { data, isPending } = authClient.useSession();
  const button = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const id = useId();
  const panelId = `mobile-menu-${id.replace(/:/g, "")}`;

  useEffect(() => {
    if (!open) return;
    panel.current?.querySelector<HTMLElement>("a,button")?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        button.current?.focus();
      }
    };
    // A click or focus anywhere outside the panel and its button closes it (so Tab can leave).
    const outside = (e: Event) => {
      const t = e.target as Node;
      if (!panel.current?.contains(t) && !button.current?.contains(t)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", outside);
    document.addEventListener("focusin", outside);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", outside);
      document.removeEventListener("focusin", outside);
    };
  }, [open]);

  const close = () => setOpen(false);
  const current = (k: Active) => (active === k ? ("page" as const) : undefined);
  const signedIn = Boolean(data?.user);

  return (
    <>
      <button
        ref={button}
        type="button"
        aria-label="Menu"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((o) => !o)}
        className="inline-flex size-10 cursor-pointer items-center justify-center rounded-[8px] text-ink hover:bg-[#F2F4F1] focus-visible:ring-2 focus-visible:ring-brand/50 focus-visible:outline-none"
      >
        <svg
          width="22"
          height="22"
          viewBox="0 0 24 24"
          aria-hidden
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        >
          {open ? <path d="M6 6l12 12M18 6L6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
        </svg>
      </button>
      <div
        ref={panel}
        id={panelId}
        hidden={!open}
        className="absolute inset-x-0 top-full z-40 border-b border-border bg-surface px-4 pt-2 pb-4 shadow-[0_12px_24px_rgba(16,26,28,.10)]"
      >
        <nav aria-label="Main" className="flex flex-col gap-0.5">
          <Link href="/" className={item} aria-current={current("stations")} onClick={close}>
            Stations
          </Link>
          <Link href="/pricing" className={item} onClick={close}>
            Map
            <span className="inline-flex items-center gap-1 rounded-full bg-premium-bg px-[7px] py-[3px] text-[10px] font-semibold tracking-[.05em] text-premium-text">
              <LockIcon />
              PRO
            </span>
          </Link>
          <Link href="/sources" className={item} aria-current={current("sources")} onClick={close}>
            Sources
          </Link>
          <Link href="/pricing" className={item} aria-current={current("pricing")} onClick={close}>
            Pricing
          </Link>
        </nav>
        <div className="mt-2 flex flex-col gap-2 border-t border-border pt-3">
          {isPending ? null : signedIn ? (
            <>
              <Link href="/account" className={item} onClick={close}>
                Account
              </Link>
              <button
                type="button"
                className={`${item} cursor-pointer text-left`}
                onClick={async () => {
                  await authClient.signOut();
                  reloadTo("/");
                }}
              >
                Sign out
              </button>
            </>
          ) : (
            <Link
              href="/pricing"
              onClick={close}
              className="inline-flex min-h-12 items-center justify-center rounded-[10px] bg-brand px-4 text-base font-semibold text-white no-underline hover:bg-brand-hover hover:text-white"
            >
              Start free trial
            </Link>
          )}
        </div>
      </div>
    </>
  );
}
