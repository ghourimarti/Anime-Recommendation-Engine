import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

// Public routes (UI redesign, route option (c) — conditional root):
//   - auth pages (else redirect loop)
//   - "/" — signed-out visitors see the marketing landing; the page component
//     branches on auth() and signed-in users get the app exactly as before
//   - marketing pages: features / pricing / about / contact / help / legal
// Everything else (/account, /checkout, /history, /api/*) still requires a
// session. Deliberately NOT public: /api/poster (the Jikan proxy would become
// an open relay) and /checkout (a plan needs an account to attach to).
const isPublicRoute = createRouteMatcher([
  "/",
  "/sign-in(.*)",
  "/sign-up(.*)",
  "/features(.*)",
  "/pricing(.*)",
  "/about(.*)",
  "/contact(.*)",
  "/help(.*)",
  "/legal(.*)",
]);

export default clerkMiddleware(async (auth, req) => {
  if (isPublicRoute(req)) return;

  // Explicit redirect (not auth.protect()): protect() returns a bare 404 when it
  // can't resolve a sign-in URL to redirect to, which surfaces as "page not
  // found" for every unauthenticated request. redirectToSignIn() always yields a
  // clean 307 to the sign-in page. The BFF /api/* routes are covered too — an
  // unauthenticated request never reaches the proxy, so the FastAPI backend
  // never sees an unauthenticated call.
  const { userId, redirectToSignIn } = await auth();
  if (!userId) {
    // Behind Docker port-mapping the standalone server binds 0.0.0.0:3000, so
    // req.url reports that internal address instead of the browser-facing
    // origin. Rebuild the return URL against the configured public origin so
    // Clerk bounces the user back to a reachable address after sign-in.
    const publicOrigin = process.env.NEXT_PUBLIC_SITE_URL;
    const returnBackUrl = publicOrigin
      ? new URL(req.nextUrl.pathname + req.nextUrl.search, publicOrigin).toString()
      : req.url;
    return redirectToSignIn({ returnBackUrl });
  }
});

export const config = {
  matcher: [
    // Skip Next internals + static files unless in search params.
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    // Always run on API + tRPC routes.
    "/(api|trpc)(.*)",
  ],
};
