"use client";

import { Clock } from "lucide-react";
import { useEffect, useState } from "react";

import { formatCountdown } from "@/lib/format";

interface QuotaNoticeProps {
  /** Seconds until the daily quota resets (from the 429 Retry-After header). */
  retryAfterSeconds: number;
}

/** The 429 state, designed: a live ticking countdown to the quota reset rather
  *  than a transient toast. This is the "friendly countdown"
 *  — the difference between a hobby app (raw error) and a product. */
export function QuotaNotice({ retryAfterSeconds }: QuotaNoticeProps) {
  const [remaining, setRemaining] = useState(retryAfterSeconds);

  useEffect(() => {
    setRemaining(retryAfterSeconds);
    const id = setInterval(() => setRemaining((r) => Math.max(0, r - 1)), 1000);
    return () => clearInterval(id);
  }, [retryAfterSeconds]);

  return (
    <div className="rounded-xl border border-primary/30 bg-primary/[0.06] p-8 text-center">
      <Clock className="mx-auto h-6 w-6 text-primary" />
      <h3 className="mt-3 font-display text-2xl">Daily limit reached</h3>
      <p className="mt-1 text-sm text-muted-foreground">
        You&apos;ve used today&apos;s free recommendations. Your quota resets in
      </p>
      <p className="mt-3 font-mono text-3xl text-primary tabular-nums">
        {formatCountdown(remaining)}
      </p>
    </div>
  );
}
