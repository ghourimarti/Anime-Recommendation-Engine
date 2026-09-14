import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import { Instrument_Serif, Inter, JetBrains_Mono } from "next/font/google";
import { Toaster } from "sonner";

import { MotionProvider } from "@/components/motion-provider";
import { SiteFooter } from "@/components/shell/site-footer";
import { SiteHeader } from "@/components/shell/site-header";
import { clerkPublishableKey, siteUrl } from "@/lib/runtime-config";
import "./globals.css";

// next/font self-hosts + preloads, exposing CSS variables consumed by the
// Tailwind fontFamily tokens. Zero layout shift, no external font request.
const display = Instrument_Serif({
  subsets: ["latin"],
  weight: "400",
  variable: "--font-display",
  display: "swap",
});
const sans = Inter({ subsets: ["latin"], variable: "--font-sans", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono", display: "swap" });

const TITLE = "ANIMA — Find your next anime";
const DESCRIPTION = "Tell us the mood. Get three grounded picks, with the reasoning.";

// Render per request, not at build: the site URL and the Clerk publishable key
// come from the container environment (lib/runtime-config.ts), so ONE image
// serves every environment. A prerendered page would freeze what the build saw.
export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  return {
    metadataBase: new URL(siteUrl()),
    title: TITLE,
    description: DESCRIPTION,
    applicationName: "ANIMA",
    // opengraph-image.tsx + icon.svg are auto-detected by the App Router.
    openGraph: { title: TITLE, description: DESCRIPTION, type: "website", siteName: "ANIMA" },
    twitter: { card: "summary_large_image", title: TITLE, description: DESCRIPTION },
  };
}

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  // ClerkProvider must wrap the whole tree and lives at the Server-Component
  // root layout (not inside a Client Component) so server helpers like auth()
  // work everywhere downstream. `dark` is forced — Cinematic Noir is dark-only.
  return (
    <ClerkProvider publishableKey={clerkPublishableKey()}>
      <html
        lang="en"
        suppressHydrationWarning
        className={`dark ${display.variable} ${sans.variable} ${mono.variable}`}
      >
        <body className="flex min-h-screen flex-col antialiased">
          {/* Film-grain overlay — fixed, non-interactive, sits above everything. */}
          <div className="noise-overlay" aria-hidden="true" />
          <SiteHeader />
          <main className="container flex-1 py-8">
            <MotionProvider>{children}</MotionProvider>
          </main>
          <SiteFooter />
          <Toaster theme="dark" richColors position="top-center" />
        </body>
      </html>
    </ClerkProvider>
  );
}
