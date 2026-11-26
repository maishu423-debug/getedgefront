import { defineConfig, devices } from "@playwright/test";

// Runs against a running stack (web + API with real data): E2E_BASE_URL, default localhost:3000.
const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:3000";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  timeout: 45_000,
  use: { baseURL, trace: "on-first-retry" },
  // Accounts tests sign in with Google against this local fake (never real Google).
  webServer: {
    command: "node e2e/fake-google.mjs",
    url: "http://localhost:4455/health",
    reuseExistingServer: true,
  },
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
