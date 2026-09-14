import { afterEach, describe, expect, it, vi } from "vitest";

import { clerkPublishableKey, configuredSiteUrl, siteUrl } from "@/lib/runtime-config";

describe("runtime-config", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("prefers the runtime SITE_URL over the dev NEXT_PUBLIC_SITE_URL", () => {
    vi.stubEnv("SITE_URL", "https://anime.example.com");
    vi.stubEnv("NEXT_PUBLIC_SITE_URL", "http://localhost:1006");
    expect(siteUrl()).toBe("https://anime.example.com");
  });

  it("falls back to NEXT_PUBLIC_SITE_URL for pnpm dev", () => {
    vi.stubEnv("SITE_URL", "");
    vi.stubEnv("NEXT_PUBLIC_SITE_URL", "http://localhost:1006");
    expect(configuredSiteUrl()).toBe("http://localhost:1006");
  });

  it("reports nothing configured and defaults to the local dev server", () => {
    vi.stubEnv("SITE_URL", "");
    vi.stubEnv("NEXT_PUBLIC_SITE_URL", "");
    expect(configuredSiteUrl()).toBeUndefined();
    expect(siteUrl()).toBe("http://localhost:3000");
  });

  it("reads the Clerk publishable key at call time, not import time", () => {
    vi.stubEnv("CLERK_PUBLISHABLE_KEY", "pk_test_one");
    expect(clerkPublishableKey()).toBe("pk_test_one");
    vi.stubEnv("CLERK_PUBLISHABLE_KEY", "pk_test_two");
    expect(clerkPublishableKey()).toBe("pk_test_two");
  });

  it("falls back to NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY for pnpm dev", () => {
    vi.stubEnv("CLERK_PUBLISHABLE_KEY", "");
    vi.stubEnv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "pk_test_dev");
    expect(clerkPublishableKey()).toBe("pk_test_dev");
  });
});
