import react from "@vitejs/plugin-react";
import { resolve } from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": resolve(__dirname, "./src") },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    // Playwright e2e lives in tests/e2e and runs via `pnpm test:e2e`, NOT here.
    include: ["tests/unit/**/*.test.{ts,tsx}"],
  },
});
