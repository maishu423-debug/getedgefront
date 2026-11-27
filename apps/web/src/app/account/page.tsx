import type { Metadata } from "next";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { Suspense } from "react";

import { AccountActions } from "@/components/account/AccountActions";
import { DeleteAccount } from "@/components/account/DeleteAccount";
import { MethodsCard } from "@/components/account/MethodsCard";
import { ProfileForm } from "@/components/account/ProfileForm";
import { SubscriptionCard } from "@/components/account/SubscriptionCard";
import { Activation } from "@/components/billing/Activation";
import { PageShell } from "@/components/Chrome";
import { Skeleton } from "@/components/states";
import { getAuth, googleEnabled } from "@/lib/auth/server";
import { getViewer } from "@/lib/auth/viewer";
import { accountBilling } from "@/lib/billing/account";

export const metadata: Metadata = { title: "Account", robots: { index: false } };

export default function AccountPage({ searchParams }: PageProps<"/account">) {
  return (
    <PageShell>
      <Suspense
        fallback={
          <main id="main" className="mx-auto w-full max-w-[880px] px-4 pt-8 pb-16 sm:px-8">
            <Skeleton className="h-[640px]" label="Loading account" />
          </main>
        }
      >
        <Content searchParams={searchParams} />
      </Suspense>
    </PageShell>
  );
}

async function Content({ searchParams }: { searchParams: PageProps<"/account">["searchParams"] }) {
  const viewer = await getViewer();
  if (!viewer.user) redirect("/signin?next=%2Faccount");
  const sp = await searchParams;
  const billing = await accountBilling(viewer.user.id, viewer.user.email);
  // Back from Stripe Checkout: Premium appears only once the webhook has been mirrored.
  const activating = sp.checkout === "success" && billing.entitlement.tier !== "premium";
  const accounts = await getAuth().api.listUserAccounts({ headers: await headers() });
  const google = accounts.find((a) => a.providerId === "google") ?? null;
  const credential = accounts.find((a) => a.providerId === "credential") ?? null;
  const u = viewer.user;
  return (
    <main
      id="main"
      className="mx-auto flex w-full max-w-[880px] flex-col gap-6 px-4 pt-8 pb-16 sm:px-8"
    >
      <div className="flex flex-col gap-1">
        <h1 className="font-display text-[34px] font-bold tracking-[-0.02em]">Account</h1>
        <span className="text-sm text-muted">{u.email}</span>
      </div>
      {activating ? <Activation /> : null}
      <SubscriptionCard billing={billing} email={u.email} emailVerified={u.emailVerified} />
      <ProfileForm name={u.name} email={u.email} emailVerified={u.emailVerified} />
      <MethodsCard
        googleEnabled={googleEnabled()}
        google={google ? { id: google.id } : null}
        password={credential ? { updatedAt: new Date(credential.updatedAt).toISOString() } : null}
        email={u.email}
      />
      <DeleteAccount hasPassword={Boolean(credential)} fresh={viewer.fresh} />
      <AccountActions />
    </main>
  );
}
