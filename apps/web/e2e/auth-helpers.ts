import { readFileSync } from "node:fs";

import { expect, type BrowserContext, type Page, type TestInfo } from "@playwright/test";

/** The web server writes emails here (EMAIL_OUTBOX_FILE); tests read links from it. */
export const OUTBOX = process.env.E2E_EMAIL_OUTBOX ?? "";
export const PASSWORD = "lighthouse-anemometer-42";
export const PASSWORD_2 = "barometer-tidal-wave-77";

export function uniqueEmail(info: TestInfo, tag: string): string {
  const rand = Math.random().toString(36).slice(2, 8);
  return `${tag}-${info.project.name}-${Date.now()}-${rand}@example.org`.toLowerCase();
}

type Mail = { kind: string; to: string; subject: string; text: string };

export function mails(to: string, kind?: string): Mail[] {
  if (!OUTBOX) throw new Error("set E2E_EMAIL_OUTBOX to the web server's EMAIL_OUTBOX_FILE");
  let raw = "";
  try {
    raw = readFileSync(OUTBOX, "utf8");
  } catch {
    return [];
  }
  // The web server appends one JSON line per email; tests in other workers read the same file and
  // may catch the last line half-written, so a line that doesn't parse yet is skipped (the next
  // poll sees it whole). Matching is by exact recipient, which is unique per test and retry.
  const out: Mail[] = [];
  for (const line of raw.split("\n")) {
    if (!line) continue;
    try {
      const m = JSON.parse(line) as Mail;
      if (m.to === to && (!kind || m.kind === kind)) out.push(m);
    } catch {
      // partial line
    }
  }
  return out;
}

/** Waits for an email of `kind` to `to` and returns the first http(s) link in its text. */
export async function linkFrom(to: string, kind: string): Promise<string> {
  let link = "";
  await expect
    .poll(
      () => {
        const m = mails(to, kind).at(-1);
        link = m?.text.match(/https?:\/\/\S+/)?.[0] ?? "";
        return link;
      },
      { timeout: 15_000 },
    )
    .not.toBe("");
  return link;
}

/** Who the fake Google signs in as for this browser context (see e2e/fake-google.mjs). */
export async function setGoogleIdentity(
  context: BrowserContext,
  identity: { sub: string; email: string; name: string; email_verified: boolean },
) {
  const value = Buffer.from(JSON.stringify(identity), "utf8").toString("base64url");
  await context.addCookies([
    { name: "fake_google_identity", value, domain: "localhost", path: "/" },
  ]);
}

export async function signUp(page: Page, name: string, email: string, password = PASSWORD) {
  await page.goto("/signin?mode=signup");
  await page.getByLabel("Name").fill(name);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/check-email\?kind=verify/);
}

export async function verify(page: Page, email: string) {
  await page.goto(await linkFrom(email, "verify"));
  await expect(page.getByRole("heading", { name: "Email confirmed" })).toBeVisible();
}

export async function signIn(page: Page, email: string, password = PASSWORD, next = "") {
  await page.goto(`/signin${next ? `?next=${encodeURIComponent(next)}` : ""}`);
  // /signin sends signed-in visitors away: fail fast and clearly if a session is still alive.
  await expect(page, "still signed in: /signin redirected away").toHaveURL(/\/signin/);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
}

export async function expectSignedIn(page: Page) {
  await expect(page.getByRole("button", { name: /Account menu/ })).toBeVisible();
}

export async function expectSignedOut(page: Page) {
  // the visible header slot (full nav from 640 px, compact row below)
  await expect(
    page.getByRole("banner").getByRole("link", { name: "Sign in", exact: true }),
  ).toBeVisible();
}

/**
 * Signs out from the header menu and waits until it has really happened. The menu awaits the
 * sign-out request and then reloads "/"; navigating away before that aborts the request and
 * leaves the session alive (slow CI runners hit this).
 */
export async function signOutFromMenu(page: Page) {
  await page.getByRole("button", { name: /Account menu/ }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/$/);
  await expectSignedOut(page);
}

/** The form's error/notice box (Next's empty route announcer also has role=alert). */
export function formAlert(page: Page) {
  return page.locator('[role="alert"]:not(#__next-route-announcer__)');
}
