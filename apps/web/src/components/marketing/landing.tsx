import {
  Clock3,
  MessageSquareQuote,
  Quote,
  ScanSearch,
  Sparkles,
  ThumbsUp,
} from "lucide-react";
import Link from "next/link";

import { Reveal, StaggerItem, StaggerList } from "@/components/reveal";
import { buttonVariants } from "@/components/ui/button";
import { EXAMPLE_PROMPTS } from "@/lib/examples";
import { posterGradient, posterInitial } from "@/lib/poster-fallback";
import { cn } from "@/lib/utils";

// The signed-out landing (route option (c)). Server Component: static content,
// no client state. The hero's "query box" is a facsimile that routes to
// /sign-up — the real box needs a session, and faking interactivity here would
// be dishonest. Poster fan uses the deterministic Noir fallback art (the real
// /api/poster proxy is auth-gated by design — see middleware.ts).
const HERO_POSTERS = ["Cowboy Bebop", "Monster", "Frieren"] as const;

const FEATURES = [
  {
    icon: MessageSquareQuote,
    title: "Ask in your own words",
    body: "No genre dropdowns, no tag matrices. Describe the mood — “a slow-burn revenge story with a clever protagonist” — and that sentence is the whole search.",
  },
  {
    icon: ScanSearch,
    title: "Grounded picks, not guesses",
    body: "Every recommendation is retrieved from a real catalog and verified before it reaches you. If a title shows up, it exists — with the reasoning attached.",
  },
  {
    icon: Sparkles,
    title: "The why, streamed live",
    body: "Each set of picks comes with a streamed explanation of why they match what you asked for. Stop it any time; it's your time and your call.",
  },
  {
    icon: ThumbsUp,
    title: "Feedback that compounds",
    body: "Thumbs up or down on any pick. Your watch history and reactions collect in one place, sharpening what we show you next.",
  },
] as const;

const STATS = [
  // Honest numbers only — these are real product properties, not invented users.
  { value: "3", label: "grounded picks per ask" },
  { value: "~5s", label: "from question to answer" },
  { value: "20/day", label: "free picks, every day" },
] as const;

// TODO: replace with real testimonials before launch — placeholder copy,
// clearly fictional names, never wired into anything that looks like live data.
const TESTIMONIALS = [
  {
    quote:
      "I stopped doom-scrolling seasonal charts. I type a feeling, I get three things worth watching, I press play.",
    name: "Placeholder — early user",
    role: "TODO: replace with real quote",
  },
  {
    quote:
      "The reasoning is the killer feature. It tells me why a show fits the ask, so I trust the pick before episode one.",
    name: "Placeholder — beta tester",
    role: "TODO: replace with real quote",
  },
] as const;

export function Landing() {
  return (
    <div className="space-y-24 pb-16 sm:space-y-32">
      {/* ── Hero: the thesis ─────────────────────────────────────────── */}
      <section className="pt-10 text-center sm:pt-20">
        <Reveal className="mx-auto max-w-3xl space-y-6">
          <p className="text-xs font-medium uppercase tracking-[0.25em] text-primary/80">
            Grounded anime discovery
          </p>
          <h1 className="text-5xl leading-[1.05] tracking-tight sm:text-6xl">
            Stop scrolling lists.
            <br />
            Say what you feel like watching.
          </h1>
          <p className="mx-auto max-w-xl text-lg text-muted-foreground">
            ANIMA turns one sentence into three real, grounded anime picks —
            with the reasoning to back them up.
          </p>
        </Reveal>

        {/* The marquee: an inert facsimile of the product's query box. */}
        <Reveal className="mx-auto mt-10 max-w-2xl space-y-4">
          <Link
            href="/sign-up"
            aria-label="Create an account to start asking"
            className="block rounded-xl ring-1 ring-border transition-shadow hover:ring-2 hover:ring-primary/60 hover:shadow-[0_0_48px_-12px] hover:shadow-primary/40"
          >
            <div className="rounded-xl bg-card/60 p-5 text-left">
              <p className="text-base text-muted-foreground">
                {EXAMPLE_PROMPTS[3]}
                <span className="ml-0.5 inline-block h-5 w-[2px] animate-pulse bg-primary align-middle" />
              </p>
            </div>
          </Link>
          <div className="flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link href="/sign-up" className={cn(buttonVariants({ size: "lg" }))}>
              Get three picks — free
            </Link>
            <Link
              href="/features"
              className={cn(buttonVariants({ variant: "ghost", size: "lg" }))}
            >
              See how it works
            </Link>
          </div>
          <p className="text-xs text-muted-foreground">
            20 asks a day, free. No card required.
          </p>
        </Reveal>

        {/* Poster fan — deterministic Noir fallback art, no external requests. */}
        <StaggerList className="mx-auto mt-14 flex max-w-lg items-end justify-center gap-4">
          {HERO_POSTERS.map((title, i) => (
            <StaggerItem key={title}>
              <div
                aria-hidden="true"
                className={cn(
                  "flex h-44 w-28 items-end justify-start rounded-lg border border-border/60 p-2 shadow-2xl sm:h-56 sm:w-36",
                  i === 1 ? "-translate-y-3 sm:-translate-y-5" : "translate-y-0",
                )}
                style={{ background: posterGradient(title) }}
              >
                <span className="font-display text-3xl text-foreground/30">
                  {posterInitial(title)}
                </span>
              </div>
            </StaggerItem>
          ))}
        </StaggerList>
      </section>

      {/* ── Features band (real capabilities only) ───────────────────── */}
      <section aria-labelledby="landing-features">
        <Reveal className="mx-auto mb-12 max-w-2xl space-y-3 text-center">
          <h2 id="landing-features" className="text-3xl tracking-tight sm:text-4xl">
            Built for the “what should I watch?” moment
          </h2>
          <p className="text-muted-foreground">
            Everything below ships today — no roadmap slides.
          </p>
        </Reveal>
        <div className="grid gap-4 sm:grid-cols-2">
          {FEATURES.map(({ icon: Icon, title, body }) => (
            <Reveal key={title}>
              <div className="h-full rounded-xl border border-border/60 bg-card/40 p-6">
                <Icon className="mb-4 h-5 w-5 text-primary" />
                <h3 className="mb-2 font-medium">{title}</h3>
                <p className="text-sm leading-relaxed text-muted-foreground">{body}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ── Stats band (honest product properties) ───────────────────── */}
      <section aria-label="Product facts" className="rounded-xl border border-border/60 bg-card/30">
        <div className="grid divide-y divide-border/60 sm:grid-cols-3 sm:divide-x sm:divide-y-0">
          {STATS.map(({ value, label }) => (
            <div key={label} className="p-8 text-center">
              <p className="font-mono text-3xl text-primary">{value}</p>
              <p className="mt-1 text-sm text-muted-foreground">{label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Social proof (clearly-marked placeholders) ───────────────── */}
      <section aria-labelledby="landing-quotes">
        <h2 id="landing-quotes" className="sr-only">
          What early users say
        </h2>
        <div className="grid gap-4 sm:grid-cols-2">
          {TESTIMONIALS.map((t) => (
            <Reveal key={t.quote}>
              <figure className="h-full rounded-xl border border-border/60 bg-card/40 p-6">
                <Quote className="mb-3 h-4 w-4 text-primary/60" />
                <blockquote className="text-sm leading-relaxed">{t.quote}</blockquote>
                <figcaption className="mt-4 text-xs text-muted-foreground">
                  {t.name} · {t.role}
                </figcaption>
              </figure>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ── Closing CTA ──────────────────────────────────────────────── */}
      <section className="rounded-xl border border-primary/20 bg-primary/[0.04] p-10 text-center sm:p-14">
        <Reveal className="mx-auto max-w-xl space-y-5">
          <Clock3 className="mx-auto h-6 w-6 text-primary" />
          <h2 className="text-3xl tracking-tight">
            Your next favorite is one sentence away
          </h2>
          <p className="text-muted-foreground">
            Free tier, every day. Upgrade only if you want more asks.
          </p>
          <div className="flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link href="/sign-up" className={cn(buttonVariants({ size: "lg" }))}>
              Start free
            </Link>
            <Link
              href="/pricing"
              className={cn(buttonVariants({ variant: "outline", size: "lg" }))}
            >
              See pricing
            </Link>
          </div>
        </Reveal>
      </section>
    </div>
  );
}
