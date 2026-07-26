import Link from "next/link";

// Shared frame for the legal pages: narrow prose column + cross-links.
const LEGAL_LINKS = [
  { href: "/legal/privacy", label: "Privacy policy" },
  { href: "/legal/terms", label: "Terms of service" },
  { href: "/legal/cookies", label: "Cookie policy" },
] as const;

export default function LegalLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto max-w-2xl space-y-8 pb-16 pt-8">
      <nav aria-label="Legal pages" className="flex flex-wrap gap-4 text-sm">
        {LEGAL_LINKS.map(({ href, label }) => (
          <Link
            key={href}
            href={href}
            className="text-muted-foreground underline-offset-4 transition-colors hover:text-foreground hover:underline"
          >
            {label}
          </Link>
        ))}
      </nav>
      <article className="space-y-6 leading-relaxed [&_h1]:text-3xl [&_h1]:tracking-tight [&_h2]:mt-8 [&_h2]:text-xl [&_h2]:tracking-tight [&_p]:text-sm [&_p]:text-muted-foreground [&_li]:text-sm [&_li]:text-muted-foreground [&_ul]:list-disc [&_ul]:space-y-1 [&_ul]:pl-5">
        {children}
      </article>
    </div>
  );
}
