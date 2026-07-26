import { describe, expect, it } from "vitest";

import { formatCountdown } from "@/lib/format";

describe("formatCountdown", () => {
  it("formats hours + minutes above an hour", () => {
    expect(formatCountdown(7200)).toBe("2h 0m");
    expect(formatCountdown(3 * 3600 + 5 * 60)).toBe("3h 5m");
  });

  it("formats minutes + seconds under an hour", () => {
    expect(formatCountdown(90)).toBe("1m 30s");
  });

  it("formats seconds only under a minute", () => {
    expect(formatCountdown(45)).toBe("45s");
  });

  it("clamps negatives to 0s", () => {
    expect(formatCountdown(-5)).toBe("0s");
    expect(formatCountdown(0)).toBe("0s");
  });
});
