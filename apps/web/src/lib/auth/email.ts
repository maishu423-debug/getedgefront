import "server-only";

import { appendFile } from "node:fs/promises";

import { logJson } from "@/lib/deploy";

import type { Email } from "./templates";

/**
 * Sends transactional email (v2 Phase 7 A). With RESEND_API_KEY set: Resend's HTTP API, from
 * EMAIL_FROM. Without it (local dev, tests): the email is printed to the console instead, or, when
 * EMAIL_OUTBOX_FILE is set, appended to that file as one JSON line (Playwright reads the links from
 * there). Production logs never contain the recipient address or the link; on Railway a missing
 * key is an error, never a fallback to the console.
 */
export async function sendEmail(email: Email): Promise<void> {
  const key = process.env.RESEND_API_KEY;
  if (!key) {
    if (process.env.RAILWAY_ENVIRONMENT_NAME) {
      // Deployed without Resend: never print sign-in links into the platform's logs.
      logJson("error", "email not sent: RESEND_API_KEY is not set", { kind: email.kind });
      throw new Error("email is not configured");
    }
    if (process.env.EMAIL_OUTBOX_FILE) {
      const line = JSON.stringify({ ts: new Date().toISOString(), ...email });
      await appendFile(process.env.EMAIL_OUTBOX_FILE, line + "\n");
    } else {
      console.log(`[email:console] ${email.kind} to ${email.to}\n${email.text}`);
    }
    return;
  }
  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { authorization: `Bearer ${key}`, "content-type": "application/json" },
    body: JSON.stringify({
      from: process.env.EMAIL_FROM,
      to: [email.to],
      subject: email.subject,
      html: email.html,
      text: email.text,
    }),
    signal: AbortSignal.timeout(10_000),
  });
  if (!res.ok) {
    logJson("error", "email send failed", { kind: email.kind, status: res.status });
    throw new Error(`email send failed (${res.status})`);
  }
  logJson("info", "email sent", { kind: email.kind });
}
