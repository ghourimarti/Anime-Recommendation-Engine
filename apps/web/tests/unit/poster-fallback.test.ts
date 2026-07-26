import { describe, expect, it } from "vitest";

import { posterGradient, posterInitial } from "@/lib/poster-fallback";

describe("posterGradient", () => {
  it("is deterministic for the same title", () => {
    expect(posterGradient("Cowboy Bebop")).toBe(posterGradient("Cowboy Bebop"));
  });

  it("differs across distinct titles", () => {
    expect(posterGradient("Monster")).not.toBe(posterGradient("One Piece"));
  });

  it("returns a CSS linear-gradient string", () => {
    expect(posterGradient("X")).toMatch(/^linear-gradient\(/);
  });
});

describe("posterInitial", () => {
  it("uppercases the first alphanumeric character", () => {
    expect(posterInitial("cowboy bebop")).toBe("C");
    expect(posterInitial("86")).toBe("8");
  });

  it("skips leading punctuation/quotes", () => {
    expect(posterInitial('"Hello"')).toBe("H");
  });

  it("falls back to ? for an empty title", () => {
    expect(posterInitial("")).toBe("?");
  });
});
