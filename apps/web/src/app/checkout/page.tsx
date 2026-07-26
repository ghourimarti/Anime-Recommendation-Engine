import type { Metadata } from "next";
import { CreditCard, Info, Lock } from "lucide-react";
import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
  title: "Checkout — ANIMA",
  description: "Review your plan and complete your subscription.",
};

// Billing is UI-complete but stubbed — no payment provider is wired yet.
// NEXT_PUBLIC_BILLING_ENABLED=false renders the full checkout shape with a
// clearly-labeled "not live" notice; flipping the flag activates the payment
// fields once a provider is integrated.
// TODO: integrate a payment provider before enabling.
const BILLING_ENABLED = process.env.NEXT_PUBLIC_BILLING_ENABLED === "true";

const PLANS: Record<string, { name: string; monthly: number }> = {
  pro: { name: "Pro", monthly: 4.99 },
  premium: { name: "Premium", monthly: 9.99 },
};

export default async function CheckoutPage({
  searchParams,
}: {
  searchParams: Promise<{ plan?: string; billing?: string }>;
}) {
  const params = await searchParams;
  const plan = PLANS[params.plan ?? "pro"] ?? PLANS.pro;
  const annual = params.billing === "annual";
  const perMonth = annual ? plan.monthly * 0.8 : plan.monthly;
  const dueToday = annual ? perMonth * 12 : perMonth;

  return (
    <div className="mx-auto max-w-lg space-y-8 pb-16 pt-8">
      <header className="space-y-2">
        <h1 className="text-3xl tracking-tight">Checkout</h1>
        <p className="text-sm text-muted-foreground">
          Review your plan, then complete payment.
        </p>
      </header>

      {/* Order summary */}
      <section
        aria-label="Order summary"
        className="rounded-xl border border-border/60 bg-card/40 p-6"
      >
        <div className="flex items-baseline justify-between">
          <div>
            <h2 className="font-medium">ANIMA {plan.name}</h2>
            <p className="text-xs text-muted-foreground">
              {annual ? "Annual billing (−20%)" : "Monthly billing"}
            </p>
          </div>
          <p className="text-right">
            <span className="font-mono text-2xl">${perMonth.toFixed(2)}</span>
            <span className="block text-xs text-muted-foreground">per month</span>
          </p>
        </div>
        <div className="mt-4 flex items-center justify-between border-t border-border/60 pt-4 text-sm">
          <span className="text-muted-foreground">Due today</span>
          <span className="font-mono">${dueToday.toFixed(2)}</span>
        </div>
        <Link
          href="/pricing"
          className="mt-3 inline-block text-xs text-muted-foreground underline-offset-4 hover:underline"
        >
          Change plan
        </Link>
      </section>

      {/* Payment — stubbed until billing is enabled */}
      <section aria-label="Payment" className="space-y-4">
        {!BILLING_ENABLED && (
          <div className="flex items-start gap-3 rounded-xl border border-primary/30 bg-primary/[0.06] p-4">
            <Info className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
            <p className="text-sm text-muted-foreground">
              Billing isn&apos;t live yet — this checkout is a preview. Your
              free plan keeps working; nothing will be charged.
            </p>
          </div>
        )}
        <fieldset
          disabled={!BILLING_ENABLED}
          className="space-y-3 rounded-xl border border-border/60 bg-card/40 p-6 disabled:opacity-50"
        >
          <legend className="sr-only">Payment details</legend>
          <label className="block text-sm">
            <span className="mb-1 block text-muted-foreground">Card number</span>
            <div className="flex items-center gap-2 rounded-md border border-input bg-background px-3 py-2">
              <CreditCard className="h-4 w-4 text-muted-foreground" />
              <input
                type="text"
                inputMode="numeric"
                placeholder="1234 5678 9012 3456"
                className="w-full bg-transparent outline-none placeholder:text-muted-foreground/50"
                autoComplete="cc-number"
              />
            </div>
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block text-sm">
              <span className="mb-1 block text-muted-foreground">Expiry</span>
              <input
                type="text"
                placeholder="MM / YY"
                className="w-full rounded-md border border-input bg-background px-3 py-2 outline-none placeholder:text-muted-foreground/50"
                autoComplete="cc-exp"
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-muted-foreground">CVC</span>
              <input
                type="text"
                inputMode="numeric"
                placeholder="123"
                className="w-full rounded-md border border-input bg-background px-3 py-2 outline-none placeholder:text-muted-foreground/50"
                autoComplete="cc-csc"
              />
            </label>
          </div>
          <button
            type="button"
            className={cn(buttonVariants({ size: "lg" }), "w-full")}
            aria-disabled={!BILLING_ENABLED}
          >
            <Lock className="h-4 w-4" />
            {BILLING_ENABLED ? `Pay $${dueToday.toFixed(2)}` : "Payments not yet enabled"}
          </button>
        </fieldset>
        <p className="flex items-center justify-center gap-1.5 text-xs text-muted-foreground">
          <Lock className="h-3 w-3" /> Payments will be processed by a PCI-compliant provider.
        </p>
      </section>
    </div>
  );
}
