import { expect, test } from "@playwright/test";

import {
  expectSignedIn,
  expectSignedOut,
  formAlert,
  linkFrom,
  mails,
  PASSWORD,
  PASSWORD_2,
  setGoogleIdentity,
  signIn,
  signOutFromMenu,
  signUp,
  uniqueEmail,
  verify,
} from "./auth-helpers";

// Accounts (v2 Phase 7). Needs the web server started with EMAIL_OUTBOX_FILE and
// E2E_FAKE_GOOGLE_URL (see infra/auth-setup.md, "Running the auth tests").
test.describe("accounts", () => {
  test.skip(!process.env.E2E_EMAIL_OUTBOX, "auth e2e needs E2E_EMAIL_OUTBOX");

  test("sign up → verify → sign out → sign in", async ({ page }, info) => {
    const email = uniqueEmail(info, "flow");
    await signUp(page, "Ada Lovelace", email);
    await expect(page.getByRole("heading", { name: "Check your email" })).toBeVisible();
    await verify(page, email);
    await expectSignedIn(page); // autoSignInAfterVerification
    await page.goto("/account");
    await expect(page.getByRole("heading", { level: 1, name: "Account" })).toBeVisible();
    await expect(page.getByText("Verified", { exact: true })).toBeVisible();
    await expect(
      page.getByText("FREE", { exact: true }).filter({ visible: true }).first(),
    ).toBeVisible();
    await page.getByRole("button", { name: "Sign out", exact: true }).click();
    await expect(page).toHaveURL(/\/$/);
    await expectSignedOut(page);
    await signIn(page, email);
    await expect(page).toHaveURL(/\/$/);
    await expectSignedIn(page);
    // signed in, the trial can't start yet (billing is Phase 8)
    await page.goto("/pricing");
    await expect(page.getByRole("button", { name: "Coming soon" })).toBeDisabled();
  });

  test("sign-up never reveals an existing email", async ({ page }, info) => {
    const email = uniqueEmail(info, "dupe");
    await signUp(page, "First", email);
    await signUp(page, "Second Try", email, PASSWORD_2); // same page, same message
    await expect(page.getByRole("heading", { name: "Check your email" })).toBeVisible();
    await expect.poll(() => mails(email, "existing_account").length).toBe(1);
    expect(mails(email, "verify")).toHaveLength(1); // no second account, no second verification
    // the original password still works; the second one does not
    await verify(page, email);
    await signOutFromMenu(page);
    await signIn(page, email, PASSWORD_2);
    await expect(formAlert(page)).toContainText("email or password is not right");
  });

  test("wrong password and unknown email get the same message", async ({ page }, info) => {
    const email = uniqueEmail(info, "enum");
    await signUp(page, "Enum Test", email);
    await signIn(page, email, "definitely-not-it-123");
    const known = await formAlert(page).innerText();
    await signIn(page, uniqueEmail(info, "nobody"), "definitely-not-it-123");
    await expect(formAlert(page)).toHaveText(known);
  });

  test("forgot password → reset → other sessions revoked", async ({ page, browser }, info) => {
    const email = uniqueEmail(info, "reset");
    await signUp(page, "Reset Me", email);
    await verify(page, email); // page is now signed in (session A)
    const other = await browser.newContext();
    const p2 = await other.newPage();
    await p2.goto("/reset-password");
    await p2.getByLabel("Email").fill(email);
    await p2.getByRole("button", { name: "Send reset link" }).click();
    await expect(p2).toHaveURL(/\/check-email\?kind=reset/);
    await p2.goto(await linkFrom(email, "reset"));
    await p2.getByLabel("New password").fill(PASSWORD_2);
    await p2.getByRole("button", { name: "Save new password" }).click();
    await expect(p2).toHaveURL(/\/signin\?reset=1/);
    await expect(p2.getByRole("status")).toContainText("Your password was changed");
    await expect.poll(() => mails(email, "password_changed").length).toBe(1);
    // session A was revoked
    await page.goto("/account");
    await expect(page).toHaveURL(/\/signin\?next=%2Faccount/);
    await signIn(p2, email, PASSWORD);
    await expect(formAlert(p2)).toBeVisible(); // old password no longer works
    await signIn(p2, email, PASSWORD_2);
    await expectSignedIn(p2);
    await other.close();
  });

  test("Google sign-in creates an account; it is the last method so it can't be removed", async ({
    page,
  }, info) => {
    const email = uniqueEmail(info, "goog");
    await setGoogleIdentity(page.context(), {
      sub: `g-${email}`,
      email,
      name: "Grace Hopper",
      email_verified: true,
    });
    await page.goto("/signin?next=%2Faccount");
    await page.getByRole("button", { name: "Continue with Google" }).click();
    await expect(page).toHaveURL(/\/account$/);
    await expect(page.getByText(`Connected as ${email}`)).toBeVisible();
    await expect(page.getByRole("button", { name: "Disconnect" })).toBeDisabled();
    await expect(page.getByText("Google is your only way to sign in")).toBeVisible();
  });

  test("link Google to a verified password account, then disconnect it", async ({ page }, info) => {
    const email = uniqueEmail(info, "link");
    await signUp(page, "Link Me", email);
    await verify(page, email);
    await page.goto("/account");
    await setGoogleIdentity(page.context(), {
      sub: `g-${email}`,
      email,
      name: "Link Me",
      email_verified: true,
    });
    await page.getByRole("button", { name: "Connect Google" }).click();
    await expect(page).toHaveURL(/\/account$/);
    await expect(page.getByText(`Connected as ${email}`)).toBeVisible();
    const disconnect = page.getByRole("button", { name: "Disconnect" });
    await expect(disconnect).toBeEnabled(); // the password remains
    await disconnect.click();
    await expect(page.getByText("Not connected")).toBeVisible();
  });

  test("Google never links to an unverified email account", async ({ page }, info) => {
    const email = uniqueEmail(info, "unver");
    await signUp(page, "Not Verified", email); // never verified
    await setGoogleIdentity(page.context(), {
      sub: `g-${email}`,
      email,
      name: "Attacker?",
      email_verified: true,
    });
    await page.goto("/signin");
    await page.getByRole("button", { name: "Continue with Google" }).click();
    await expect(page).toHaveURL(/\/signin.*error=/);
    await expect(formAlert(page)).toContainText("already an EdgeFront account with this email");
    await expectSignedOut(page);
  });

  test("change password signs out other sessions and sends a notice", async ({
    page,
    browser,
  }, info) => {
    const email = uniqueEmail(info, "chg");
    await signUp(page, "Change Me", email);
    await verify(page, email);
    const other = await browser.newContext();
    const p2 = await other.newPage();
    await signIn(p2, email);
    await expectSignedIn(p2);
    await page.goto("/account");
    await page.getByRole("button", { name: "Change password" }).click();
    await page.getByLabel("Current password").fill(PASSWORD);
    await page.getByLabel("New password").fill("1234567890"); // common → refused
    await page.locator("#pw-form").getByRole("button", { name: "Change password" }).click();
    await expect(page.getByText("This password is too common")).toBeVisible();
    await page.getByLabel("New password").fill(PASSWORD_2);
    await page.locator("#pw-form").getByRole("button", { name: "Change password" }).click();
    await expect(page.getByRole("status")).toContainText("Password changed");
    await expect.poll(() => mails(email, "password_changed").length).toBe(1);
    await p2.goto("/account");
    await expect(p2).toHaveURL(/\/signin/);
    await other.close();
  });

  test("delete account", async ({ page }, info) => {
    const email = uniqueEmail(info, "del");
    await signUp(page, "Delete Me", email);
    await verify(page, email); // fresh session: no password needed
    await page.goto("/account");
    await page.getByRole("button", { name: "Delete account" }).click();
    await page.getByRole("button", { name: "Delete my account permanently" }).click();
    await expect(page).toHaveURL(/\/\?account=deleted/);
    await expectSignedOut(page);
    await expect.poll(() => mails(email, "account_deleted").length).toBe(1);
    await signIn(page, email);
    await expect(formAlert(page)).toContainText("email or password is not right");
  });

  test("per-email rate limit on sign-in", async ({ page }, info) => {
    const email = uniqueEmail(info, "rl");
    await signUp(page, "Rate Limited", email);
    let message = "";
    for (let i = 0; i < 12; i++) {
      await signIn(page, email, `wrong-password-${i}xx`);
      message = await formAlert(page).innerText({ timeout: 10_000 });
      if (message.includes("Too many attempts")) break;
    }
    expect(message).toContain("Too many attempts");
  });

  test("?next= returns to same-site paths only", async ({ page }, info) => {
    const email = uniqueEmail(info, "next");
    await signUp(page, "Next Test", email);
    await signIn(page, email, PASSWORD, "/station/KDFW");
    await expect(page).toHaveURL(/\/station\/KDFW$/);
    await signOutFromMenu(page);
    await signIn(page, email, PASSWORD, "//evil.example.com/steal");
    await expect(page).toHaveURL(/^http:\/\/localhost:3000\/$/);
  });

  test("account pages need a session; free pages never do", async ({ page }) => {
    await page.goto("/account");
    await expect(page).toHaveURL(/\/signin\?next=%2Faccount/);
    for (const p of ["/", "/station/KDFW", "/sources", "/pricing"]) {
      const res = await page.goto(p);
      expect(res?.status()).toBe(200);
    }
    await expect(page.getByRole("link", { name: "Start free trial" }).last()).toHaveAttribute(
      "href",
      "/signin?next=%2Fpricing",
    );
  });

  test("header has no layout shift while the session loads", async ({ page }, info) => {
    const email = uniqueEmail(info, "cls");
    await signUp(page, "Layout Shift", email);
    await verify(page, email);
    // Signed in (avatar) and signed out (Sign in + Start free trial): the slot is the same size
    // from the first paint, so the header never moves anything.
    for (const signedIn of [true, false]) {
      if (!signedIn) {
        await signOutFromMenu(page);
      }
      for (const p of ["/", "/pricing", "/station/KDFW"]) {
        await page.goto(p);
        if (signedIn) await expectSignedIn(page);
        else await expectSignedOut(page);
        const shifts = await page.evaluate(
          () =>
            new Promise<{ total: number; header: number }>((resolve) => {
              const out = { total: 0, header: 0 };
              type Shift = { value: number; hadRecentInput: boolean; sources: { node?: Node }[] };
              new PerformanceObserver((list) => {
                for (const e of list.getEntries() as unknown as Shift[]) {
                  if (e.hadRecentInput) continue;
                  out.total += e.value;
                  if (
                    e.sources.some(
                      (s) => s.node && document.querySelector("header")?.contains(s.node),
                    )
                  )
                    out.header += e.value;
                }
              }).observe({ type: "layout-shift", buffered: true });
              setTimeout(() => resolve(out), 500);
            }),
        );
        expect(shifts.header, `header CLS on ${p}`).toBe(0);
        // /pricing has no live data, so the whole page must be still.
        if (p === "/pricing") expect(shifts.total, "CLS on /pricing").toBeLessThan(0.01);
      }
    }
  });
});
