import { auth } from "@clerk/nextjs/server";
import { Suspense } from "react";

import { Landing } from "@/components/marketing/landing";
import { QueryExperience } from "@/components/query-experience";

// Root route branches on session:
//   signed-in  → the app
//   signed-out → the marketing landing (middleware allows "/" unauthenticated)
// force-dynamic: the branch depends on the request's session, never cacheable.
export const dynamic = "force-dynamic";

export default async function HomePage() {
  const { userId } = await auth();

  if (!userId) {
    return <Landing />;
  }

  // Suspense boundary: QueryExperience reads useSearchParams (?q= prefill),
  // which Next requires be wrapped so the route can still stream/prerender.
  return (
    <Suspense fallback={null}>
      <QueryExperience />
    </Suspense>
  );
}
