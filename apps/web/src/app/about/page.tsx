import type { Metadata } from "next";
import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
  title: "About — ANIMA",
  description: "Why ANIMA exists: discovery should start with how you feel, not with a database.",
};

export default function AboutPage() {
  return (
    <div className="mx-auto max-w-2xl space-y-10 pb-16 pt-8">
      <header className="space-y-4">
        <h1 className="text-4xl tracking-tight">
          Discovery should start with a feeling
        </h1>
        <p className="text-lg text-muted-foreground">
          The anime world has extraordinary databases and no good answers to
          the only question that matters at 9pm: “what should I watch tonight?”
        </p>
      </header>

      <section className="space-y-4 leading-relaxed text-muted-foreground">
        <p>
          Every anime platform is built database-first — tags, filters,
          seasonal charts, ranked lists. They&apos;re wonderful archives and
          terrible advisors. You arrive with a mood and leave forty minutes
          later with fifteen open tabs and no episode started.
        </p>
        <p>
          ANIMA inverts that. You describe what you feel like watching, in your
          own words, and get three picks grounded in a real catalog — each with
          the reasoning spelled out. Not a hundred maybes. Three, with a why.
        </p>
        <p>
          We&apos;re honest about the machinery: recommendations are AI-retrieved
          and verified against real titles before you see them, limits are
          stated with exact reset times, and when the engine degrades we say so
          instead of pretending. Trust is the product.
        </p>
      </section>

      <section className="rounded-xl border border-border/60 bg-card/40 p-6">
        <h2 className="mb-3 text-xl tracking-tight">The principles</h2>
        <ul className="space-y-2 text-sm text-muted-foreground">
          <li>· Language in, picks out — no filter matrices.</li>
          <li>· Grounded or dropped — no hallucinated titles.</li>
          <li>· Reasoning shown, always — no black-box scores.</li>
          <li>· Honest degradation — no fake certainty.</li>
        </ul>
      </section>

      <div>
        <Link href="/sign-up" className={cn(buttonVariants())}>
          Try it free
        </Link>
      </div>
    </div>
  );
}
