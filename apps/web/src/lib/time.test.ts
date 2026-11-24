import { describe, expect, it } from "vitest";

import { formatZulu } from "./time";

describe("formatZulu", () => {
  it("formats UTC hours and minutes", () => {
    expect(formatZulu("2026-11-24T21:05:12Z")).toBe("21:05Z");
  });

  it("converts offsets to UTC", () => {
    expect(formatZulu("2026-11-24T15:05:00-06:00")).toBe("21:05Z");
  });

  it("shows missing as a dash", () => {
    expect(formatZulu(null)).toBe("—");
    expect(formatZulu(undefined)).toBe("—");
    expect(formatZulu("")).toBe("—");
    expect(formatZulu("not a date")).toBe("—");
  });
});
