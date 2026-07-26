import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";
import { posterGradient, posterInitial } from "@/lib/poster-fallback";
import { cn } from "@/lib/utils";

// Branded 404 — in-universe copy, a Noir fallback "poster" as the visual, and
// two clear exits. Server Component; no state.
export default function NotFound() {
  return (
    <div className="flex flex-col items-center gap-6 py-24 text-center">
      <div
        aria-hidden="true"
        className="flex h-40 w-28 items-end rounded-lg border border-border/60 p-2 shadow-2xl"
        style={{ background: posterGradient("404 Lost Episode") }}
      >
        <span className="font-display text-3xl text-foreground/30">
          {posterInitial("404")}
        </span>
      </div>
      <div className="space-y-2">
        <p className="font-mono text-sm text-primary">404</p>
        <h1 className="text-3xl tracking-tight">This episode doesn&apos;t exist</h1>
        <p className="max-w-sm text-sm text-muted-foreground">
          The page you&apos;re looking for was never animated. Head back and
          ask for something we can actually find.
        </p>
      </div>
      <div className="flex gap-3">
        <Link href="/" className={cn(buttonVariants())}>
          Go home
        </Link>
        <Link href="/help" className={cn(buttonVariants({ variant: "outline" }))}>
          Help center
        </Link>
      </div>
    </div>
  );
}
