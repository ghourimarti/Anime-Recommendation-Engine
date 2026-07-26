import type { Metadata } from "next";

import { ContactForm } from "@/components/marketing/contact-form";

export const metadata: Metadata = {
  title: "Contact — ANIMA",
  description: "Questions, bugs, billing — write to us and we'll reply by email.",
};

export default function ContactPage() {
  return (
    <div className="mx-auto max-w-lg space-y-8 pb-16 pt-8">
      <header className="space-y-3">
        <h1 className="text-4xl tracking-tight">Contact</h1>
        <p className="text-muted-foreground">
          Bug reports, billing questions, or a recommendation we got badly
          wrong — we read everything.
        </p>
      </header>
      <ContactForm />
    </div>
  );
}
