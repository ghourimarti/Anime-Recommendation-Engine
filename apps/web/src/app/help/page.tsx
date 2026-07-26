import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Help — ANIMA",
  description: "How ANIMA works: asks, picks, limits, history, and account questions.",
};

const GROUPS = [
  {
    heading: "Using ANIMA",
    items: [
      {
        q: "How do I get recommendations?",
        a: "Type what you feel like watching into the box on the home page — a mood, a genre blend, a comparison (“like X but darker”) — and submit. You'll get three picks grounded in a real catalog, each with a short why-it-matches.",
      },
      {
        q: "What makes a good query?",
        a: "Specifics beat labels. “A psychological thriller under 24 episodes” or “cozy slice-of-life to unwind to” both work better than one-word genres. The example chips under the box are good starting shapes.",
      },
      {
        q: "What is the streamed explanation?",
        a: "After your picks land, ANIMA can stream a longer explanation of why they fit your ask. It renders live; the Stop button genuinely cancels the generation, not just the display.",
      },
      {
        q: "Why did I get a “popular picks” fallback?",
        a: "When the recommendation engine can't answer confidently (or is having an incident), we say so and serve widely-loved titles instead of guessing. The notice on the result marks it clearly.",
      },
    ],
  },
  {
    heading: "Limits & plans",
    items: [
      {
        q: "How many asks do I get?",
        a: "Free accounts get 20 asks per UTC day. When you hit the limit, the exact reset time is shown. Paid plans raise the ceiling — see Pricing.",
      },
      {
        q: "Do unused asks roll over?",
        a: "No — the counter resets at midnight UTC every day.",
      },
    ],
  },
  {
    heading: "Account & data",
    items: [
      {
        q: "Where is my watch history?",
        a: "Watchlist, in the header. Every ask and its picks are saved to your account, newest first.",
      },
      {
        q: "How do I change my email or password?",
        a: "Click your avatar in the header → Manage account. Sign-in methods, email, and security all live there.",
      },
      {
        q: "How do I delete my data?",
        a: "Write to us via the contact page from your account email and we'll process deletion. The privacy policy describes exactly what is stored.",
      },
    ],
  },
] as const;

export default function HelpPage() {
  return (
    <div className="mx-auto max-w-2xl space-y-10 pb-16 pt-8">
      <header className="space-y-3">
        <h1 className="text-4xl tracking-tight">Help center</h1>
        <p className="text-muted-foreground">
          Short answers to the common questions. Not covered?{" "}
          <Link href="/contact" className="text-primary underline-offset-4 hover:underline">
            Contact us
          </Link>
          .
        </p>
      </header>

      {GROUPS.map((group) => (
        <section key={group.heading} aria-label={group.heading} className="space-y-3">
          <h2 className="text-xl tracking-tight">{group.heading}</h2>
          <div className="divide-y divide-border/60 rounded-xl border border-border/60">
            {group.items.map(({ q, a }) => (
              <details key={q} className="group p-5">
                <summary className="cursor-pointer list-none text-sm font-medium">
                  {q}
                </summary>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{a}</p>
              </details>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
