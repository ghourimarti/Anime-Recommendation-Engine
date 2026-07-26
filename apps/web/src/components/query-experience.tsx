"use client";

import { AlertTriangle, Loader2, Wand2 } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { QuotaNotice } from "@/components/quota-notice";
import { RecommendationCard } from "@/components/recommendation-card";
import { Reveal, StaggerItem, StaggerList } from "@/components/reveal";
import { StreamingExplanation } from "@/components/streaming-explanation";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { EXAMPLE_PROMPTS } from "@/lib/examples";
import type { RecommendResponse } from "@/lib/types";

/** The product: preference input → structured recommendations (cards) →
 * optional streamed explanation. Client Component for the interactivity; the
 * page shell around it stays server-rendered. */
export function QueryExperience() {
  // Seed the box from ?q=… so the command-palette prompts (and shareable links)
  // prefill the query. useSearchParams requires a <Suspense> boundary (page.tsx).
  const searchParams = useSearchParams();
  const [query, setQuery] = useState(searchParams.get("q") ?? "");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<RecommendResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [quotaSeconds, setQuotaSeconds] = useState<number | null>(null);

  async function submit() {
    const trimmed = query.trim();
    if (!trimmed) return;
    setLoading(true);
    setResult(null);
    setError(null);
    setQuotaSeconds(null);
    try {
      const res = await fetch("/api/recommend", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: trimmed }),
      });
      if (res.status === 429) {
        const retry = Number(res.headers.get("Retry-After") ?? "0");
        setQuotaSeconds(Number.isFinite(retry) && retry > 0 ? retry : 0);
        return;
      }
      if (!res.ok) throw new Error(`request failed (${res.status})`);
      const data: RecommendResponse = await res.json();
      setResult(data);
      if (data.degraded && data.notice) toast.warning(data.notice);
    } catch {
      setError("Couldn't fetch recommendations. Check your connection and try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-8">
      {/* Hero spotlight */}
      <Reveal className="space-y-3 pt-6 text-center sm:pt-10">
        <p className="text-xs font-medium uppercase tracking-[0.2em] text-primary/80">
          Grounded anime discovery
        </p>
        <h1 className="text-4xl leading-tight tracking-tight sm:text-5xl">
          What do you feel like watching?
        </h1>
        <p className="mx-auto max-w-md text-muted-foreground">
          Describe a vibe — we&apos;ll ground three picks in real anime, with the reasoning.
        </p>
      </Reveal>

      <div className="space-y-3">
        {/* Glowing query box: amber ring on focus via the focus-within ring. */}
        <div className="rounded-xl ring-1 ring-border transition-shadow focus-within:ring-2 focus-within:ring-primary/60 focus-within:shadow-[0_0_40px_-12px] focus-within:shadow-primary/30">
          <Textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. a slow-burn revenge story with a clever protagonist"
            rows={3}
            className="resize-none border-0 bg-card/60 text-base focus-visible:ring-0 focus-visible:ring-offset-0"
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
            }}
          />
        </div>

        {/* Example-prompt chips */}
        <div className="flex flex-wrap gap-2">
          {EXAMPLE_PROMPTS.map((prompt) => (
            <button
              key={prompt}
              type="button"
              onClick={() => setQuery(prompt)}
              className="rounded-full border border-border/70 bg-secondary/40 px-3 py-1 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
            >
              {prompt}
            </button>
          ))}
        </div>

        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">
            <kbd className="rounded border border-border bg-secondary px-1 font-mono">⌘↵</kbd> to
            submit
          </span>
          <Button type="button" onClick={submit} disabled={loading || !query.trim()}>
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" /> Finding picks…
              </>
            ) : (
              <>
                <Wand2 className="h-4 w-4" /> Get recommendations
              </>
            )}
          </Button>
        </div>
      </div>

      {loading && (
        <div className="space-y-4">
          {[0, 1, 2].map((i) => (
            <Card key={i} className="overflow-hidden">
              <div className="flex">
                <Skeleton className="h-40 w-24 shrink-0 rounded-none sm:w-32" />
                <div className="flex-1 space-y-3 p-4">
                  <Skeleton className="h-4 w-16" />
                  <Skeleton className="h-6 w-2/3" />
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="h-4 w-1/2" />
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {!loading && quotaSeconds !== null && <QuotaNotice retryAfterSeconds={quotaSeconds} />}

      {!loading && error && (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-destructive/30 bg-destructive/[0.06] p-8 text-center">
          <AlertTriangle className="h-6 w-6 text-destructive" />
          <p className="text-sm text-muted-foreground">{error}</p>
          <Button variant="outline" size="sm" onClick={submit}>
            Try again
          </Button>
        </div>
      )}

      {!loading && result && (
        <div className="space-y-4">
          <StaggerList className="space-y-4">
            {result.recommendations.map((rec, i) => (
              <StaggerItem key={rec.mal_id}>
                <RecommendationCard
                  rec={rec}
                  queryHistoryId={result.query_history_id}
                  rank={i + 1}
                  priority={i === 0}
                />
              </StaggerItem>
            ))}
          </StaggerList>
          {result.recommendations.length > 0 && (
            <StreamingExplanation query={result.query} />
          )}
        </div>
      )}
    </div>
  );
}
