import { defineConfig, devices } from "@playwright/test";

// Runs against a running stack (web + API with real data): E2E_BASE_URL, default localhost:3000.
const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:3000";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  // A test that only passes on retry is a bug, not a pass: CI fails on flaky tests.
  failOnFlakyTests: !!process.env.CI,
  reporter: "list",
  timeout: 45_000,
  // Failed and retried tests keep a trace and a screenshot (uploaded as CI artifacts).
  use: { baseURL, trace: "retain-on-failure", screenshot: "only-on-failure" },
  // Local fakes, never the real services: Google sign-in (accounts) and Stripe (billing).
  webServer: [
    {
      command: "node e2e/fake-google.mjs",
      url: "http://localhost:4455/health",
      reuseExistingServer: true,
    },
    {
      command: "node e2e/fake-stripe.mjs",
      url: "http://localhost:4466/health",
      reuseExistingServer: true,
    },
  ],
  projects: [
    {
      name: "desktop-1440",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
    {
      name: "phone-375",
      use: { ...devices["Desktop Chrome"], viewport: { width: 375, height: 812 }, hasTouch: true },
    },
  ],
});
