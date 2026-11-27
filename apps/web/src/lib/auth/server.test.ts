import { describe, expect, it, vi } from "vitest";

import { e2eFakeGoogleUrl } from "./server";

vi.mock("server-only", () => ({}));

describe("e2eFakeGoogleUrl (the test-only fake Google can never run in production)", () => {
  it("is off unless set", () => expect(e2eFakeGoogleUrl({})).toBeNull());
  it("accepts localhost", () => {
    expect(e2eFakeGoogleUrl({ E2E_FAKE_GOOGLE_URL: "http://localhost:4455" })).toBe(
      "http://localhost:4455",
    );
    expect(e2eFakeGoogleUrl({ E2E_FAKE_GOOGLE_URL: "http://127.0.0.1:4455" })).toBeTruthy();
  });
  it.each(["https://fake.example.com", "http://localhost.evil.example:4455", "not a url"])(
    "refuses %s",
    (url) => expect(() => e2eFakeGoogleUrl({ E2E_FAKE_GOOGLE_URL: url })).toThrow(),
  );
  it("refuses on Railway even for localhost", () =>
    expect(() =>
      e2eFakeGoogleUrl({
        E2E_FAKE_GOOGLE_URL: "http://localhost:4455",
        RAILWAY_ENVIRONMENT_NAME: "production",
      }),
    ).toThrow());
});
