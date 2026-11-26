/**
 * Transactional email templates (v2 Phase 7 A). Plain, accessible HTML (one column, real text,
 * no images, no tracking pixels) plus a text version. Copy is operational, not legal.
 */

export interface Email {
  kind: "verify" | "reset" | "password_changed" | "account_deleted" | "existing_account";
  to: string;
  subject: string;
  html: string;
  text: string;
}

const ESC: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};
const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ESC[c]!);

function layout(title: string, paragraphs: string[], button?: { label: string; url: string }) {
  const body = paragraphs
    .map((p) => `<p style="margin:0 0 16px;line-height:1.5">${esc(p)}</p>`)
    .join("");
  const cta = button
    ? `<p style="margin:24px 0"><a href="${esc(button.url)}" style="display:inline-block;background:#0A6E69;color:#ffffff;padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:600">${esc(button.label)}</a></p>` +
      `<p style="margin:0 0 16px;line-height:1.5;font-size:13px;color:#4A5552">If the button does not work, copy this link into your browser:<br><span style="word-break:break-all">${esc(button.url)}</span></p>`
    : "";
  return (
    `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>${esc(title)}</title></head>` +
    `<body style="margin:0;padding:24px;background:#F4F5F2;color:#101A1C;font-family:Arial,Helvetica,sans-serif;font-size:16px">` +
    `<div style="max-width:560px;margin:0 auto;background:#ffffff;border:1px solid #DDE1DC;border-radius:12px;padding:28px">` +
    `<p style="margin:0 0 20px;font-weight:700;font-size:18px">EdgeFront</p><h1 style="margin:0 0 16px;font-size:20px">${esc(title)}</h1>` +
    body +
    cta +
    `<p style="margin:24px 0 0;font-size:13px;color:#4A5552">EdgeFront · getedgefront.com. You received this because of an action on your EdgeFront account.</p>` +
    `</div></body></html>`
  );
}

function plain(title: string, paragraphs: string[], link?: string) {
  return [
    "EdgeFront",
    "",
    title,
    "",
    ...paragraphs.flatMap((p) => [p, ""]),
    ...(link ? [link, ""] : []),
    "EdgeFront · getedgefront.com",
  ].join("\n");
}

function make(
  kind: Email["kind"],
  to: string,
  subject: string,
  title: string,
  paragraphs: string[],
  button?: { label: string; url: string },
): Email {
  return {
    kind,
    to,
    subject,
    html: layout(title, paragraphs, button),
    text: plain(title, paragraphs, button?.url),
  };
}

export const verifyEmail = (to: string, url: string) =>
  make(
    "verify",
    to,
    "Confirm your EdgeFront email",
    "Confirm your email",
    [
      "Confirm this address to finish setting up your EdgeFront account. The link works for 24 hours.",
      "If you did not create an account, you can ignore this email.",
    ],
    { label: "Confirm email", url },
  );

export const resetPassword = (to: string, url: string) =>
  make(
    "reset",
    to,
    "Reset your EdgeFront password",
    "Reset your password",
    [
      "Someone asked to reset the password for this EdgeFront account. The link works for 1 hour and can be used once.",
      "If it was not you, ignore this email; your password stays the same.",
    ],
    { label: "Choose a new password", url },
  );

export const passwordChanged = (to: string, signInUrl: string) =>
  make(
    "password_changed",
    to,
    "Your EdgeFront password was changed",
    "Your password was changed",
    [
      "The password for your EdgeFront account was just changed, and you were signed out on your other devices.",
      "If you did not do this, reset your password right away from the sign-in page.",
    ],
    { label: "Go to sign in", url: signInUrl },
  );

export const accountDeleted = (to: string) =>
  make("account_deleted", to, "Your EdgeFront account was deleted", "Your account was deleted", [
    "Your EdgeFront account and its sign-in details have been deleted. You can keep using the free pages without an account.",
    "If you did not ask for this, reply to this email.",
  ]);

export const existingAccount = (to: string, signInUrl: string, resetUrl: string) =>
  make(
    "existing_account",
    to,
    "You already have an EdgeFront account",
    "You already have an account",
    [
      "Someone tried to create an EdgeFront account with this email, but you already have one. Nothing was changed.",
      "Sign in with your existing account, or reset your password if you have forgotten it.",
      `Reset your password: ${resetUrl}`,
    ],
    { label: "Sign in", url: signInUrl },
  );
