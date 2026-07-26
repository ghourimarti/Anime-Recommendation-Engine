import { defineConfig } from "@playwright/test";

// e2e only — points at tests/e2e so it never collides with the Vitest unit
// suite in tests/unit. Gated on E2E_BASE_URL (see recommend.spec.ts).
export default defineConfig({
  testDir: "./tests/e2e",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "on-first-retry",
  },
});
