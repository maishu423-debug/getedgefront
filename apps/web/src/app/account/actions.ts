"use server";

import { headers } from "next/headers";

import { COMMON_PASSWORDS } from "@/lib/auth/common-passwords";
import { PASSWORD_MESSAGES, passwordProblem } from "@/lib/auth/password";
import { getAuth } from "@/lib/auth/server";

/**
 * Set a password for an account that signs in with Google only (Better Auth exposes setPassword
 * on the server only). The same rules as sign-up apply. Requires the current session.
 */
export async function setPasswordAction(
  newPassword: string,
): Promise<{ ok: boolean; error?: string }> {
  const problem = passwordProblem(newPassword, COMMON_PASSWORDS);
  if (problem) return { ok: false, error: PASSWORD_MESSAGES[problem] };
  try {
    await getAuth().api.setPassword({ body: { newPassword }, headers: await headers() });
    return { ok: true };
  } catch {
    return { ok: false, error: "Could not set the password. Sign in again and retry." };
  }
}
