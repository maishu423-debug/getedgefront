import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { AuthShell } from "@/components/auth/forms";
import { PageShell } from "@/components/Chrome";
import { Skeleton } from "@/components/states";
import { safeNext } from "@/lib/auth/redirect";

export const metadata: Metadata = { title: "Email confirmation", robots: { index: false } };

/** Better Auth's confirmation link (/api/auth/verify-email) redirects here, with ?error= when
 * the link was invalid or expired. */
export default function VerifyEmailPage({ searchParams }: PageProps<"/verify-email">) {
  return (
    <PageShell>
      <Suspense
        fallback={
          <AuthShell>
            <Skeleton className="h-[200px]" />
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
  searchParams: PageProps<"/verify-email">["searchParams"];
}) {
  const sp = await searchParams;
  const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);
  const failed = Boolean(one(sp.error));
  const next = safeNext(one(sp.next), "/");
  return (
    <AuthShell>
      <h1 className="font-display text-[26px] font-bold tracking-[-0.02em]">
        {failed ? "This link didn't work" : "Email confirmed"}
      </h1>
      <p className="text-sm leading-relaxed text-text-2">
        {failed
          ? "The confirmation link is invalid or has expired. Sign in and send a new one from your account page."
          : "Thanks. Your email address is confirmed and you're signed in."}
      </p>
      <Link href={failed ? "/signin" : next} className="text-sm font-semibold">
        {failed ? "Go to sign in" : "Continue"}
      </Link>
    </AuthShell>
  );
}
