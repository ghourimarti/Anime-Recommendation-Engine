import { Diamond } from "lucide-react";
import Link from "next/link";

// Multi-column commercial footer (3B). Columns follow the Product / Company /
// Resources / Legal anatomy; the status row keeps the original heartbeat dot.
const COLUMNS = [
  {
    heading: "Product",
    links: [
      { href: "/features", label: "Features" },
      { href: "/pricing", label: "Pricing" },
      { href: "/history", label: "Watchlist" },
    ],
  },
  {
    heading: "Company",
    links: [
      { href: "/about", label: "About" },
      { href: "/contact", label: "Contact" },
    ],
  },
  {
    heading: "Resources",
    links: [
      { href: "/help", label: "Help center" },
      { href: "/sign-up", label: "Create account" },
    ],
  },
  {
    heading: "Legal",
    links: [
      { href: "/legal/privacy", label: "Privacy policy" },
      { href: "/legal/terms", label: "Terms of service" },
      { href: "/legal/cookies", label: "Cookie policy" },
    ],
  },
] as const;

export function SiteFooter() {
  return (
    <footer className="border-t border-border/60">
      <div className="container grid gap-10 py-12 sm:grid-cols-2 lg:grid-cols-5">
        <div className="space-y-3 lg:col-span-1">
          <Link href="/" className="flex items-center gap-2 font-display text-lg tracking-wide">
            <Diamond className="h-3.5 w-3.5 fill-primary text-primary" />
            ANIMA
          </Link>
          <p className="max-w-xs text-xs leading-relaxed text-muted-foreground">
            Say what you feel like watching. Get three grounded picks, with the
            reasoning.
          </p>
        </div>
        {COLUMNS.map((col) => (
          <nav key={col.heading} aria-label={col.heading} className="space-y-3">
            <h3 className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              {col.heading}
            </h3>
            <ul className="space-y-2">
              {col.links.map(({ href, label }) => (
                <li key={href}>
                  <Link
                    href={href}
                    className="text-sm text-muted-foreground transition-colors hover:text-foreground"
                  >
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        ))}
      </div>
      <div className="border-t border-border/40">
        <div className="container flex h-14 items-center justify-between text-xs text-muted-foreground">
          <span>© {new Date().getFullYear()} ANIMA · grounded anime recommendations</span>
          <span className="inline-flex items-center gap-1.5">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success/60" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-success" />
            </span>
            All systems operational
          </span>
        </div>
      </div>
    </footer>
  );
}
