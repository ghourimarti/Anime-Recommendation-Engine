"use client";

import { Check, Minus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// Client component: the monthly/annual toggle is the only state. Prices are
// UI placeholders until billing goes live (checkout is stubbed behind
// NEXT_PUBLIC_BILLING_ENABLED — see /checkout).
// Annual = monthly × 12 × 0.8, shown as the effective per-month price.
const ANNUAL_DISCOUNT = 0.8;

type Tier = {
  id: "free" | "pro" | "premium";
  name: string;
  monthly: number;
  blurb: string;
  cta: string;
  highlight: boolean;
  features: string[];
};

const TIERS: Tier[] = [
  {
    id: "free",
    name: "Free",
    monthly: 0,
    blurb: "For the nightly “what should I watch?”",
    cta: "Start free",
    highlight: false,
    features: ["20 asks per day", "3 grounded picks per ask", "Watch history", "Thumbs feedback"],
  },
  {
    id: "pro",
    name: "Pro",
    monthly: 4.99,
    blurb: "For binge planners and seasonal completionists.",
    cta: "Choose Pro",
    highlight: true,
    features: [
      "200 asks per day",
      "Everything in Free",
      "Longer, deeper explanations",
      "Priority during peak hours",
    ],
  },
  {
    id: "premium",
    name: "Premium",
    monthly: 9.99,
    blurb: "For the person the group chat asks first.",
    cta: "Choose Premium",
    highlight: false,
    features: [
      "Unlimited asks (fair use)",
      "Everything in Pro",
      "Early access to new features",
      "Priority support",
    ],
  },
];

const COMPARISON: { label: string; free: string | boolean; pro: string | boolean; premium: string | boolean }[] = [
  { label: "Daily asks", free: "20", pro: "200", premium: "Unlimited*" },
  { label: "Grounded picks per ask", free: "3", pro: "3", premium: "3" },
  { label: "Streamed explanations", free: true, pro: true, premium: true },
  { label: "Watch history", free: true, pro: true, premium: true },
  { label: "Deeper explanations", free: false, pro: true, premium: true },
  { label: "Peak-hour priority", free: false, pro: true, premium: true },
  { label: "Early access", free: false, pro: false, premium: true },
  { label: "Priority support", free: false, pro: false, premium: true },
];

function price(monthly: number, annual: boolean): string {
  if (monthly === 0) return "$0";
  const effective = annual ? monthly * ANNUAL_DISCOUNT : monthly;
  return `$${effective.toFixed(2)}`;
}

function Cell({ v }: { v: string | boolean }) {
  if (v === true) return <Check className="mx-auto h-4 w-4 text-success" aria-label="Included" />;
  if (v === false) return <Minus className="mx-auto h-4 w-4 text-muted-foreground/40" aria-label="Not included" />;
  return <span className="font-mono text-sm">{v}</span>;
}

export function PricingTable() {
  const [annual, setAnnual] = useState(true);

  return (
    <div className="space-y-14">
      {/* Billing-period toggle */}
      <div className="flex items-center justify-center gap-3">
        <span className={cn("text-sm", !annual ? "text-foreground" : "text-muted-foreground")}>
          Monthly
        </span>
        <button
          type="button"
          role="switch"
          aria-checked={annual}
          aria-label="Toggle annual billing"
          onClick={() => setAnnual((v) => !v)}
          className={cn(
            "relative h-6 w-11 rounded-full transition-colors",
            annual ? "bg-primary" : "bg-secondary",
          )}
        >
          <span
            className={cn(
              "absolute top-0.5 h-5 w-5 rounded-full bg-background transition-transform",
              annual ? "translate-x-[22px]" : "translate-x-0.5",
            )}
          />
        </button>
        <span className={cn("text-sm", annual ? "text-foreground" : "text-muted-foreground")}>
          Annual <span className="text-primary">−20%</span>
        </span>
      </div>

      {/* Tier cards */}
      <div className="grid gap-4 lg:grid-cols-3">
        {TIERS.map((tier) => (
          <div
            key={tier.id}
            className={cn(
              "flex flex-col rounded-xl border bg-card/40 p-6",
              tier.highlight
                ? "border-primary/50 shadow-[0_0_48px_-16px] shadow-primary/30"
                : "border-border/60",
            )}
          >
            {tier.highlight && (
              <span className="mb-3 self-start rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary">
                Most popular
              </span>
            )}
            <h3 className="font-display text-2xl">{tier.name}</h3>
            <p className="mt-1 min-h-10 text-sm text-muted-foreground">{tier.blurb}</p>
            <p className="mt-4">
              <span className="font-mono text-4xl">{price(tier.monthly, annual)}</span>
              {tier.monthly > 0 && (
                <span className="text-sm text-muted-foreground">
                  {" "}
                  / month{annual && ", billed annually"}
                </span>
              )}
            </p>
            <ul className="my-6 space-y-2.5">
              {tier.features.map((f) => (
                <li key={f} className="flex items-start gap-2 text-sm">
                  <Check className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                  {f}
                </li>
              ))}
            </ul>
            <Link
              href={
                tier.id === "free"
                  ? "/sign-up"
                  : `/checkout?plan=${tier.id}&billing=${annual ? "annual" : "monthly"}`
              }
              className={cn(
                buttonVariants({ variant: tier.highlight ? "default" : "outline" }),
                "mt-auto w-full",
              )}
            >
              {tier.cta}
            </Link>
          </div>
        ))}
      </div>

      {/* Comparison table — scrolls inside its own container on small screens */}
      <div className="overflow-x-auto rounded-xl border border-border/60">
        <table className="w-full min-w-[560px] text-left">
          <caption className="sr-only">Feature comparison across plans</caption>
          <thead className="border-b border-border/60 bg-card/40">
            <tr>
              <th scope="col" className="p-4 text-sm font-medium">
                Feature
              </th>
              {TIERS.map((t) => (
                <th key={t.id} scope="col" className="p-4 text-center text-sm font-medium">
                  {t.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border/40">
            {COMPARISON.map((row) => (
              <tr key={row.label}>
                <th scope="row" className="p-4 text-sm font-normal text-muted-foreground">
                  {row.label}
                </th>
                <td className="p-4 text-center">
                  <Cell v={row.free} />
                </td>
                <td className="p-4 text-center">
                  <Cell v={row.pro} />
                </td>
                <td className="p-4 text-center">
                  <Cell v={row.premium} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-center text-xs text-muted-foreground">
        * Unlimited within fair use — abuse limits protect everyone&apos;s latency.
      </p>
    </div>
  );
}
