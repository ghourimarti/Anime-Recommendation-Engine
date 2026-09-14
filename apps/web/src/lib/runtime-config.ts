/**
 * Runtime configuration — read per request, never at build time (Phase 6, R2).
 *
 * `NEXT_PUBLIC_*` values are inlined into the bundle when `next build` runs, so an
 * image built with them is tied to one Clerk instance and one hostname. These
 * helpers read the container environment instead, so a single image serves kind,
 * DOKS and EKS. The `NEXT_PUBLIC_*` fallbacks keep `pnpm dev` working with the
 * existing `.env`. Server-side only: the root layout and the middleware.
 */

const DEFAULT_SITE_URL = "http://localhost:3000";

/** Browser-facing origin as configured, or undefined when nothing is set. */
export function configuredSiteUrl(): string | undefined {
  return process.env.SITE_URL || process.env.NEXT_PUBLIC_SITE_URL || undefined;
}

/** Browser-facing origin, defaulting to the local dev server. */
export function siteUrl(): string {
  return configuredSiteUrl() ?? DEFAULT_SITE_URL;
}

/** Clerk publishable key — public by design, but still per environment. */
export function clerkPublishableKey(): string | undefined {
  return (
    process.env.CLERK_PUBLISHABLE_KEY || process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY || undefined
  );
}
