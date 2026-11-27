"use client";

import { createAuthClient } from "better-auth/react";

/**
 * Browser side of Better Auth. Talks only to this site's /api/auth/* (same origin).
 * "google" is the real Google provider in every environment except end-to-end tests, where the
 * server registers a local fake under the same id — the browser code is identical either way.
 */
export const authClient = createAuthClient();

export function signInWithGoogle(callbackURL: string, errorCallbackURL: string) {
  return authClient.signIn.social({ provider: "google", callbackURL, errorCallbackURL });
}

export function linkGoogle(callbackURL: string) {
  return authClient.linkSocial({ provider: "google", callbackURL });
}

/**
 * Full page load after the session changed (sign in, sign out, password reset, account deleted).
 * Deliberately not router.push(): the client router cache may still hold pages rendered for the
 * previous session (e.g. /account), and a fresh load also resets every session-dependent widget.
 */
export function reloadTo(path: string) {
  window.location.assign(path);
}
