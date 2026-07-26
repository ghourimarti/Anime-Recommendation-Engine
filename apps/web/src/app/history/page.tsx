import { auth } from "@clerk/nextjs/server";
import { Clapperboard } from "lucide-react";
import Link from "next/link";

import { RecommendationCard } from "@/components/recommendation-card";
import { buttonVariants } from "@/components/ui/button";
import { authedBackendFetch } from "@/lib/proxy";
import type { HistoryResponse } from "@/lib/types";

// Server Component: fetches history server-side (no client useEffect flash, no
// token in the browser). Uses the React Server Component data-fetch pattern
// calls for. force-dynamic because the data is per-user + always fresh.
export const dynamic = "force-dynamic";

async function fetchHistory(): Promise<HistoryResponse | null> {
  // Call the backend directly via the shared proxy helper (we're already on the
  // server — no need to round-trip through our own /api/history route).
  const res = await authedBackendFetch("/v1/history?limit=20&offset=0");
  if (!res.ok) return null;
  return (await res.json()) as HistoryResponse;
}

export default async function HistoryPage() {
  const { userId } = await auth();
  if (!userId) return null; // middleware already redirects; this is belt-and-braces.

  const history = await fetchHistory();

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <h1 className="text-3xl tracking-tight">Your Watchlist</h1>

      {!history || history.items.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-border/60 bg-card/40 p-12 text-center">
          <Clapperboard className="h-8 w-8 text-muted-foreground" />
          <h3 className="font-display text-xl">No searches yet</h3>
          <p className="max-w-sm text-sm text-muted-foreground">
            Your recommendations will collect here once you start exploring.
          </p>
          <Link href="/" className={buttonVariants({ size: "sm" })}>
            Find anime
          </Link>
        </div>
      ) : (
        <div className="space-y-8">
          {history.items.map((item) => (
            <section key={item.id} className="space-y-3">
              <header className="space-y-1">
                <p className="font-medium">&ldquo;{item.query}&rdquo;</p>
                <time className="text-xs text-muted-foreground">
                  {new Date(item.created_at).toLocaleString()}
                </time>
              </header>
              <div className="space-y-3">
                {item.recommendations.map((rec, i) => (
                  <RecommendationCard
                    key={`${item.id}-${rec.mal_id}`}
                    rec={rec}
                    queryHistoryId={item.id}
                    showFeedback={false}
                    rank={i + 1}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
