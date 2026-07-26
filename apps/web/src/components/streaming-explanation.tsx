"use client";

import { Loader2, Square } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useStreamingExplanation } from "@/lib/use-recommend";

interface StreamingExplanationProps {
  query: string;
}

/** Optional, user-triggered prose explanation that streams token-by-token from
 * the BFF SSE route. A SEPARATE intent from the structured cards (so it's not a
  * duplicate LLM call) — this is where the streaming UX lives. */
export function StreamingExplanation({ query }: StreamingExplanationProps) {
  const { status, text, error, retryAfterSeconds, start, stop, reset } =
    useStreamingExplanation();

  if (status === "idle") {
    return (
      <Button type="button" variant="outline" onClick={() => start(query)}>
        Explain these picks
      </Button>
    );
  }

  return (
    <div className="space-y-2 rounded-lg border border-border bg-muted/40 p-4">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">Why we picked these</span>
        {status === "streaming" ? (
          <Button type="button" variant="ghost" size="sm" onClick={stop}>
            <Square className="h-3 w-3" /> Stop
          </Button>
        ) : (
          <Button type="button" variant="ghost" size="sm" onClick={reset}>
            Dismiss
          </Button>
        )}
      </div>

      {status === "quota" && (
        <p className="text-sm text-destructive">
          Daily limit reached
          {retryAfterSeconds
            ? ` — resets in ~${Math.ceil(retryAfterSeconds / 3600)}h.`
            : "."}
        </p>
      )}
      {status === "error" && (
        <p className="text-sm text-destructive">{error ?? "Something went wrong."}</p>
      )}

      {(status === "streaming" || status === "done") && (
        <p
          className="whitespace-pre-wrap text-sm text-muted-foreground"
          aria-live="polite"
          aria-busy={status === "streaming"}
        >
          {text}
          {status === "streaming" && (
            <Loader2 className="ml-1 inline h-3 w-3 animate-spin" />
          )}
        </p>
      )}
    </div>
  );
}
