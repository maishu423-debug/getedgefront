/** Password rules (v2 Phase 7 A). Pure, so the browser form and the server share them; the
 * common-password list itself is server-only (`common-passwords.ts`). */

export const PASSWORD_MIN = 10;
export const PASSWORD_MAX = 128;

export type PasswordProblem = "too_short" | "too_long" | "too_common";

export const PASSWORD_MESSAGES: Record<PasswordProblem, string> = {
  too_short: `Use at least ${PASSWORD_MIN} characters.`,
  too_long: `Use at most ${PASSWORD_MAX} characters.`,
  too_common: "This password is too common. Choose one that is harder to guess.",
};

/** Length is counted in characters (code points), so emoji and accents count once. */
export function passwordProblem(
  password: string,
  common?: ReadonlySet<string>,
): PasswordProblem | null {
  const length = [...password].length;
  if (length < PASSWORD_MIN) return "too_short";
  if (length > PASSWORD_MAX) return "too_long";
  if (common?.has(password.toLowerCase())) return "too_common";
  return null;
}
