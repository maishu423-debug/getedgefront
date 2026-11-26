"use client";

import { useState } from "react";

import { authClient, reloadTo } from "@/lib/auth/client";

import { smallBtn } from "./ProfileForm";

/** Sign out here, or everywhere (revokes every session of this account, this one included). */
export function AccountActions() {
  const [busy, setBusy] = useState(false);
  return (
    <div className="flex flex-wrap gap-2">
      <button
        type="button"
        className={smallBtn}
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          await authClient.signOut();
          reloadTo("/");
        }}
      >
        Sign out
      </button>
      <button
        type="button"
        className={smallBtn}
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          await authClient.revokeSessions();
          await authClient.signOut();
          reloadTo("/signin");
        }}
      >
        Sign out of all devices
      </button>
    </div>
  );
}
