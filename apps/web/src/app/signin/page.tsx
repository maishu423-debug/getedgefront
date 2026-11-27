import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { Suspense } from "react";

import { AuthShell } from "@/components/auth/forms";
import { SignInForm } from "@/components/auth/SignInForm";
import { PageShell } from "@/components/Chrome";
import { Skeleton } from "@/components/states";
import { safeNext } from "@/lib/auth/redirect";
import { googleEnabled } from "@/lib/auth/server";
import { getViewer } from "@/lib/auth/viewer";

export const metadata: Metadata = {
  title: "Sign in",
  description: "Sign in or create an EdgeFront account.",
  robots: { index: false },
};

export default function SignInPage({ searchParams }: PageProps<"/signin">) {
  return (
    <PageShell>
      <Suspense
        fallback={
          <AuthShell>
            <Skeleton className="h-[460px]" label="Loading sign-in" />
          </AuthShell>
        }
      >
        <Content searchParams={searchParams} />
      </Suspense>
    </PageShell>
  );
}

async function Content({ searchParams }: { searchParams: PageProps<"/signin">["searchParams"] }) {
  const sp = await searchParams;
  const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);
  const next = safeNext(one(sp.next), "/");
  const viewer = await getViewer();
  if (viewer.user) redirect(next);
  return (
    <AuthShell>
      <SignInForm
        next={next}
        googleEnabled={googleEnabled()}
        initialMode={one(sp.mode) === "signup" ? "signup" : "signin"}
        initialError={one(sp.error) ?? null}
        notice={
          one(sp.reset) === "1" ? "Your password was changed. Sign in with the new one." : null
        }
      />
    </AuthShell>
  );
}
