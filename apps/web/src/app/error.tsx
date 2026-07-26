"use client";

import { RotateCcw } from "lucide-react";
import Link from "next/link";
import { useEffect } from "react";

import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// Branded error boundary (Next.js requires this be a Client Component).
// `reset()` re-renders the failed segment — a real recovery, not a reload hint.
export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Surfaced in the browser console for bug reports; server logs carry the
    // full trace via the request id.
    console.error(error);
  }, [error]);

  return (
    <div className="flex flex-col items-center gap-6 py-24 text-center">
      <div className="space-y-2">
        <p className="font-mono text-sm text-destructive">500</p>
        <h1 className="text-3xl tracking-tight">The reel snapped</h1>
        <p className="max-w-sm text-sm text-muted-foreground">
          Something broke on our side while rendering this page. Try again —
          if it keeps happening, tell us and mention what you were doing.
        </p>
        {error.digest && (
          <p className="font-mono text-xs text-muted-foreground/60">ref: {error.digest}</p>
        )}
      </div>
      <div className="flex gap-3">
        <Button onClick={reset}>
          <RotateCcw className="h-4 w-4" /> Try again
        </Button>
        <Link href="/contact" className={cn(buttonVariants({ variant: "outline" }))}>
          Report it
        </Link>
      </div>
    </div>
  );
}
