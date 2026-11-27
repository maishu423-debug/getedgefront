import type { Metadata } from "next";
import { Suspense } from "react";

import { AuthShell } from "@/components/auth/forms";
import { ResetPasswordForm } from "@/components/auth/ResetPasswordForm";
import { PageShell } from "@/components/Chrome";
import { Skeleton } from "@/components/states";

export const metadata: Metadata = { title: "Reset your password", robots: { index: false } };

export default function ResetPasswordPage({ searchParams }: PageProps<"/reset-password">) {
  return (
    <PageShell>
      <Suspense
        fallback={
          <AuthShell>
            <Skeleton className="h-[260px]" />
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
  searchParams: PageProps<"/reset-password">["searchParams"];
}) {
  const sp = await searchParams;
  const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);
  return (
    <AuthShell>
      <ResetPasswordForm token={one(sp.token) ?? null} linkError={one(sp.error) ?? null} />
    </AuthShell>
  );
}
