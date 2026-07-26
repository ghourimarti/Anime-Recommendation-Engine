"use client";

import { ThumbsDown, ThumbsUp } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import type { FeedbackRequest } from "@/lib/types";

interface FeedbackButtonsProps {
  malId: number;
  queryHistoryId: number | null;
}

/** Thumbs up/down on a recommendation. Optimistic: the choice is reflected
 * instantly; a failed POST rolls it back and toasts. */
export function FeedbackButtons({ malId, queryHistoryId }: FeedbackButtonsProps) {
  const [rating, setRating] = useState<1 | -1 | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(next: 1 | -1) {
    const previous = rating;
    setRating(next); // optimistic
    setPending(true);
    try {
      const payload: FeedbackRequest = {
        query_history_id: queryHistoryId,
        mal_id: malId,
        rating: next,
      };
      const res = await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(`feedback failed (${res.status})`);
    } catch {
      setRating(previous); // rollback
      toast.error("Couldn't save your feedback — try again.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex items-center gap-1">
      <Button
        type="button"
        variant={rating === 1 ? "default" : "ghost"}
        size="icon"
        disabled={pending}
        aria-label="thumbs up"
        onClick={() => submit(1)}
      >
        <ThumbsUp className="h-4 w-4" />
      </Button>
      <Button
        type="button"
        variant={rating === -1 ? "destructive" : "ghost"}
        size="icon"
        disabled={pending}
        aria-label="thumbs down"
        onClick={() => submit(-1)}
      >
        <ThumbsDown className="h-4 w-4" />
      </Button>
    </div>
  );
}
