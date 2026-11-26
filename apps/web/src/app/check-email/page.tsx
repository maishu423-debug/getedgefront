import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { AuthShell } from "@/components/auth/forms";
import { PageShell } from "@/components/Chrome";
import { Skeleton } from "@/components/states";

export const metadata: Metadata = { title: "Check your email", robots: { index: false } };

export default function CheckEmailPage({ searchParams }: PageProps<"/check-email">) {
  return (
    <PageShell>
      <Suspense
        fallback={
          <AuthShell>
            <Skeleton className="h-[220px]" />
          </AuthShell>
        }
      >
        <Content searchParams={searchParams} />
      </Suspense>
    </PageShell>
  );
}

async function Content({
  searchParams,
}: {
  searchParams: PageProps<"/check-email">["searchParams"];
}) {
  const sp = await searchParams;
  const reset = (Array.isArray(sp.kind) ? sp.kind[0] : sp.kind) === "reset";
  return (
    <AuthShell>
      <span
        className="inline-flex size-12 items-center justify-center rounded-full bg-brand-tint"
        aria-hidden
      >
        <svg
          width="24"
          height="24"
          viewBox="0 0 24 24"
          fill="none"
          stroke="#0A6E69"
          strokeWidth="2"
        >
          <rect x="3" y="5" width="18" height="14" rx="2" />
          <path d="M3 7l9 6 9-6" />
        </svg>
      </span>
      <h1 className="font-display text-[26px] font-bold tracking-[-0.02em]">Check your email</h1>
      <p className="text-sm leading-relaxed text-text-2">
        {reset
          ? "If an account exists for that address, a reset link is on its way. It works for 1 hour. It may take a minute; check your spam folder too."
          : "We sent a link to confirm your email address. Open it to finish setting up your account. It may take a minute; check your spam folder too."}
      </p>
      <Link href="/signin" className="text-sm font-semibold">
        Back to sign in
      </Link>
    </AuthShell>
  );
}
