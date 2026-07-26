import type { Metadata } from "next";
import {
  History,
  MessageSquareQuote,
  ScanSearch,
  ShieldCheck,
  Sparkles,
  ThumbsUp,
} from "lucide-react";
import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
  title: "Features — ANIMA",
  description:
    "Natural-language anime discovery: grounded picks, streamed reasoning, watch history, and honest failure modes.",
};

// Deeper per-feature presentation (3D). Every section describes a REAL shipped
// capability — no roadmap features on this page.
const SECTIONS = [
  {
    icon: MessageSquareQuote,
    title: "Language-first discovery",
    lead: "The search box speaks your language.",
    body: "Every other anime site starts with a database you have to browse — filters, tags, seasonal charts. ANIMA starts with a sentence. “Cozy slice-of-life to unwind to” is a complete, valid query, and the picks come back shaped to it.",
  },
  {
    icon: ScanSearch,
    title: "Grounded recommendations",
    lead: "If we recommend it, it exists.",
    body: "Picks are retrieved from a real catalog and verified against it before you see them. A recommendation that can't be traced back to a real title is dropped, not dressed up. That's the difference between a recommendation and a hallucination.",
  },
  {
    icon: Sparkles,
    title: "Reasoning, streamed",
    lead: "See why, not just what.",
    body: "After your three picks land, ANIMA streams an explanation of why they match what you asked — live, token by token, with a stop button that actually stops the work (and the spend) instead of just hiding it.",
  },
  {
    icon: History,
    title: "A watchlist that builds itself",
    lead: "Every ask is saved to your history.",
    body: "Your past queries and their picks collect on the Watchlist page — per-account, private, and paginated. Come back Thursday and pick up the thread you started Monday.",
  },
  {
    icon: ThumbsUp,
    title: "Feedback that matters",
    lead: "Thumbs carry weight.",
    body: "Rate any pick up or down. Feedback is stored against your account and feeds evaluation of the recommendation quality — the product is measured, not vibes-tested.",
  },
  {
    icon: ShieldCheck,
    title: "Honest when things degrade",
    lead: "No fake certainty.",
    body: "If the recommendation engine is having a bad moment, ANIMA says so and serves a clearly-labeled fallback instead of pretending. Rate limits come with exact reset times. Errors tell you how to recover.",
  },
] as const;

export default function FeaturesPage() {
  return (
    <div className="space-y-16 pb-16">
      <header className="mx-auto max-w-2xl space-y-4 pt-8 text-center">
        <h1 className="text-4xl tracking-tight sm:text-5xl">
          What ANIMA actually does
        </h1>
        <p className="text-lg text-muted-foreground">
          Six capabilities, all live today. Nothing on this page is a mockup.
        </p>
      </header>

      <div className="mx-auto max-w-3xl space-y-6">
        {SECTIONS.map(({ icon: Icon, title, lead, body }) => (
          <section
            key={title}
            aria-label={title}
            className="rounded-xl border border-border/60 bg-card/40 p-8"
          >
            <Icon className="mb-4 h-6 w-6 text-primary" />
            <h2 className="text-2xl tracking-tight">{title}</h2>
            <p className="mt-1 text-sm font-medium text-primary/90">{lead}</p>
            <p className="mt-3 leading-relaxed text-muted-foreground">{body}</p>
          </section>
        ))}
      </div>

      <div className="text-center">
        <Link href="/sign-up" className={cn(buttonVariants({ size: "lg" }))}>
          Try it free
        </Link>
      </div>
    </div>
  );
}
