import type { Metadata } from "next";
import { currentUser } from "@clerk/nextjs/server";
import { BadgeCheck, CreditCard, Receipt, Settings2, UserRound } from "lucide-react";
import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
  title: "Account — ANIMA",
  description: "Your profile, preferences, and subscription.",
};

// Protected by middleware (not in the public matcher). Profile identity comes
// from Clerk; subscription state is a Free-plan placeholder until billing is
// live (the daily quota — 20/day — is enforced server-side by the API, which
// is the real source of truth; the number here mirrors that contract).
export const dynamic = "force-dynamic";

export default async function AccountPage() {
  const user = await currentUser();
  const email = user?.emailAddresses[0]?.emailAddress ?? "—";
  const name = user?.fullName || user?.username || "there";

  return (
    <div className="mx-auto max-w-2xl space-y-6 pb-16 pt-4">
      <header className="space-y-1">
        <h1 className="text-3xl tracking-tight">Account</h1>
        <p className="text-sm text-muted-foreground">
          Profile, preferences, and your plan.
        </p>
      </header>

      {/* Profile */}
      <section
        aria-labelledby="account-profile"
        className="rounded-xl border border-border/60 bg-card/40 p-6"
      >
        <div className="mb-4 flex items-center gap-2">
          <UserRound className="h-4 w-4 text-primary" />
          <h2 id="account-profile" className="font-medium">
            Profile
          </h2>
        </div>
        <dl className="space-y-2 text-sm">
          <div className="flex justify-between">
            <dt className="text-muted-foreground">Name</dt>
            <dd>{name}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-muted-foreground">Email</dt>
            <dd>{email}</dd>
          </div>
        </dl>
        <p className="mt-4 text-xs text-muted-foreground">
          Name, email, and sign-in methods are managed through the account
          menu in the header (your avatar → Manage account).
        </p>
      </section>

      {/* Subscription */}
      <section
        aria-labelledby="account-plan"
        className="rounded-xl border border-border/60 bg-card/40 p-6"
      >
        <div className="mb-4 flex items-center gap-2">
          <CreditCard className="h-4 w-4 text-primary" />
          <h2 id="account-plan" className="font-medium">
            Subscription
          </h2>
        </div>
        <div className="flex items-center justify-between rounded-lg border border-border/60 bg-background/60 p-4">
          <div>
            <p className="flex items-center gap-1.5 text-sm font-medium">
              Free plan <BadgeCheck className="h-4 w-4 text-success" />
            </p>
            <p className="text-xs text-muted-foreground">
              20 asks per day · resets midnight UTC
            </p>
          </div>
          <Link href="/pricing" className={cn(buttonVariants({ size: "sm" }))}>
            Upgrade
          </Link>
        </div>
        <p className="mt-3 text-xs text-muted-foreground">
          Downgrades and cancellation will appear here once billing is live.
        </p>
      </section>

      {/* Invoices — placeholder until billing is live */}
      <section
        aria-labelledby="account-invoices"
        className="rounded-xl border border-border/60 bg-card/40 p-6"
      >
        <div className="mb-4 flex items-center gap-2">
          <Receipt className="h-4 w-4 text-primary" />
          <h2 id="account-invoices" className="font-medium">
            Invoices
          </h2>
        </div>
        <p className="text-sm text-muted-foreground">
          No invoices yet — you&apos;re on the free plan. Paid invoices will be
          listed here with downloadable receipts.
        </p>
      </section>

      {/* Preferences */}
      <section
        aria-labelledby="account-prefs"
        className="rounded-xl border border-border/60 bg-card/40 p-6"
      >
        <div className="mb-4 flex items-center gap-2">
          <Settings2 className="h-4 w-4 text-primary" />
          <h2 id="account-prefs" className="font-medium">
            Preferences
          </h2>
        </div>
        <ul className="space-y-3 text-sm">
          <li className="flex items-center justify-between">
            <span>Theme</span>
            <span className="text-muted-foreground">Cinematic dark (only mode)</span>
          </li>
          <li className="flex items-center justify-between">
            <span>Reduced motion</span>
            <span className="text-muted-foreground">Follows your system setting</span>
          </li>
        </ul>
      </section>
    </div>
  );
}
