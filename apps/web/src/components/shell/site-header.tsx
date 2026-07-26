import { SignedIn, SignedOut, SignInButton, UserButton } from "@clerk/nextjs";
import { Diamond } from "lucide-react";
import Link from "next/link";

import { CommandPalette } from "@/components/command-palette";
import { MobileNav } from "@/components/shell/mobile-nav";
import { buttonVariants } from "@/components/ui/button";

// Marketing links shown to everyone; the app links (palette, watchlist) only
// appear signed-in. One header serves both worlds — Clerk's SignedIn/SignedOut
// components split the states without any client-side auth logic of our own.
export const MARKETING_LINKS = [
  { href: "/features", label: "Features" },
  { href: "/pricing", label: "Pricing" },
  { href: "/help", label: "Help" },
] as const;

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-50 border-b border-border/60 bg-background/80 backdrop-blur-sm">
      <div className="container flex h-16 items-center justify-between">
        <div className="flex items-center gap-8">
          <Link
            href="/"
            className="flex items-center gap-2 font-display text-xl tracking-wide"
          >
            <Diamond className="h-4 w-4 fill-primary text-primary" />
            ANIMA
          </Link>
          {/* Public marketing nav — desktop */}
          <nav className="hidden items-center gap-6 md:flex" aria-label="Main">
            {MARKETING_LINKS.map(({ href, label }) => (
              <Link
                key={href}
                href={href}
                className="text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                {label}
              </Link>
            ))}
          </nav>
        </div>

        <div className="flex items-center gap-3 sm:gap-4">
          <SignedIn>
            <CommandPalette />
            <Link
              href="/history"
              className="hidden text-sm text-muted-foreground transition-colors hover:text-foreground sm:inline"
            >
              Watchlist
            </Link>
            <Link
              href="/account"
              className="hidden text-sm text-muted-foreground transition-colors hover:text-foreground sm:inline"
            >
              Account
            </Link>
            <UserButton afterSignOutUrl="/" />
          </SignedIn>
          <SignedOut>
            <SignInButton mode="modal">
              <button className="text-sm font-medium transition-colors hover:text-primary">
                Sign in
              </button>
            </SignInButton>
            <Link href="/sign-up" className={buttonVariants({ size: "sm" })}>
              Get started
            </Link>
          </SignedOut>
          <MobileNav />
        </div>
      </div>
    </header>
  );
}
