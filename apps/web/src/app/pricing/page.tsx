import type { Metadata } from "next";

import { PricingTable } from "@/components/marketing/pricing-table";

export const metadata: Metadata = {
  title: "Pricing — ANIMA",
  description:
    "Start free with 20 asks a day. Upgrade for more asks, deeper explanations, and peak-hour priority.",
};

const FAQ = [
  {
    q: "What counts as an “ask”?",
    a: "One submitted query — you type what you feel like watching, we return three grounded picks. The streamed explanation for those picks is included in the same ask.",
  },
  {
    q: "What happens when I hit the daily limit?",
    a: "You'll see exactly when the limit resets (midnight UTC), and your history stays available. Nothing is lost — you just can't submit new asks until reset or upgrade.",
  },
  {
    q: "Can I cancel anytime?",
    a: "Yes. Paid plans are month-to-month (or annual); cancelling stops the next renewal and you keep paid features until the period ends.",
  },
  {
    q: "Is there a refund policy?",
    a: "If something's broken and we can't fix it for you, we refund the current period. Write to us via the contact page.",
  },
  {
    q: "Do you sell my watch history?",
    a: "No. Your queries and feedback improve your own picks. See the privacy policy for the full data story.",
  },
] as const;

export default function PricingPage() {
  return (
    <div className="space-y-16 pb-16">
      <header className="mx-auto max-w-2xl space-y-4 pt-8 text-center">
        <h1 className="text-4xl tracking-tight sm:text-5xl">
          Pay for asks, not for promises
        </h1>
        <p className="text-lg text-muted-foreground">
          Every plan gets the same grounded quality. Paid plans buy more asks
          and more depth.
        </p>
      </header>

      <PricingTable />

      <section aria-labelledby="pricing-faq" className="mx-auto max-w-2xl">
        <h2 id="pricing-faq" className="mb-6 text-center text-2xl tracking-tight">
          Pricing questions
        </h2>
        <div className="divide-y divide-border/60 rounded-xl border border-border/60">
          {FAQ.map(({ q, a }) => (
            <details key={q} className="group p-5">
              <summary className="cursor-pointer list-none text-sm font-medium marker:hidden">
                {q}
              </summary>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{a}</p>
            </details>
          ))}
        </div>
      </section>
    </div>
  );
}
