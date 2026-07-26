"use client";

import { Star } from "lucide-react";

import { FeedbackButtons } from "@/components/feedback-buttons";
import { Poster } from "@/components/poster";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import type { RecommendationOut } from "@/lib/types";
import { useAnimeMeta } from "@/lib/use-anime-meta";

interface RecommendationCardProps {
  rec: RecommendationOut;
  queryHistoryId: number | null;
  /** Hide the feedback control on the read-only history page. */
  showFeedback?: boolean;
  /** Eager-load this poster (the first card, above the fold) for a better LCP. */
  priority?: boolean;
  /** 1-based position in the backend's ranked result (honest — it's the real
   *  MMR ordering, not a fabricated match percentage). */
  rank?: number;
}

export function RecommendationCard({
  rec,
  queryHistoryId,
  showFeedback = true,
  priority = false,
  rank,
}: RecommendationCardProps) {
  const { meta } = useAnimeMeta(rec.mal_id);
  // MAL canonical URL — the source link (citations are part of the RAG contract;
  // every rec traces back to a real corpus entry).
  const malUrl = `https://myanimelist.net/anime/${rec.mal_id}`;

  return (
    <Card className="group overflow-hidden border-border/60 transition-all duration-300 hover:-translate-y-1 hover:border-primary/40 hover:shadow-xl hover:shadow-primary/20">
      <div className="flex">
        {/* Poster column — stretches to the card height (flex align-stretch). */}
        <div className="relative w-24 shrink-0 sm:w-32">
          <Poster malId={rec.mal_id} title={rec.title} priority={priority} fill className="h-full" />
          {/* Scrim: fade the poster's right edge into the card surface. */}
          <div className="pointer-events-none absolute inset-y-0 -right-px w-10 bg-gradient-to-r from-transparent to-card" />
        </div>

        <div className="flex min-w-0 flex-1 flex-col gap-2 p-4">
          {/* Meta row: honest rank + REAL MyAnimeList community score. */}
          <div className="flex items-center gap-2">
            {rank !== undefined && (
              <span className="rounded-sm bg-primary px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-primary-foreground">
                #{rank} Pick
              </span>
            )}
            {meta.score !== null && (
              <span className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground">
                <Star className="h-3 w-3 fill-primary text-primary" />
                {meta.score.toFixed(2)}
              </span>
            )}
          </div>

          <CardTitle className="font-display text-xl leading-tight">
            <a
              href={malUrl}
              target="_blank"
              rel="noreferrer"
              className="transition-colors hover:text-primary"
            >
              {rec.title}
            </a>
          </CardTitle>

          {/* Real genre chips + episode count (Jikan). */}
          {(meta.genres.length > 0 || meta.episodes !== null) && (
            <div className="flex flex-wrap items-center gap-1.5">
              {meta.genres.slice(0, 3).map((genre) => (
                <span
                  key={genre}
                  className="rounded-full border border-border/70 px-2 py-0.5 text-[11px] text-muted-foreground"
                >
                  {genre}
                </span>
              ))}
              {meta.episodes !== null && (
                <span className="text-[11px] text-muted-foreground">· {meta.episodes} eps</span>
              )}
            </div>
          )}

          <CardDescription className="line-clamp-2">{rec.summary}</CardDescription>

          {/* The RAG reasoning — the product's actual value, highlighted in an
              amber callout so it reads as the headline, not a footnote. */}
          <div className="rounded-md border-l-2 border-primary/60 bg-primary/[0.06] py-2 pl-3 pr-2">
            <p className="text-sm">
              <span className="font-medium text-primary">Why this matches&nbsp;&nbsp;</span>
              <span className="text-muted-foreground">{rec.why_match}</span>
            </p>
          </div>

          {showFeedback && (
            <div className="flex justify-end">
              <FeedbackButtons malId={rec.mal_id} queryHistoryId={queryHistoryId} />
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}
