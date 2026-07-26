"use client";

import { Loader2, Send } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

// Working form UI with a STUBBED submission — there is no contact endpoint on
// the backend yet (per the redesign brief: stub, don't fabricate).
// TODO: wire to a real endpoint (e.g. POST /v1/contact or a support inbox)
// before launch; until then the submission is acknowledged locally.
export function ContactForm() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim() || !message.trim()) return;
    setSending(true);
    // Simulated latency so the UI states are real even though delivery is stubbed.
    await new Promise((r) => setTimeout(r, 600));
    setSending(false);
    setEmail("");
    setMessage("");
    toast.success("Message recorded — we'll reply by email.", {
      description: "Note: contact delivery is in preview during the beta.",
    });
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <label className="block text-sm">
        <span className="mb-1 block text-muted-foreground">Your email</span>
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none placeholder:text-muted-foreground/50 focus-visible:ring-2 focus-visible:ring-ring"
          autoComplete="email"
        />
      </label>
      <label className="block text-sm">
        <span className="mb-1 block text-muted-foreground">How can we help?</span>
        <Textarea
          required
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          rows={5}
          placeholder="Billing question, bug report, a show we should know about…"
        />
      </label>
      <Button type="submit" disabled={sending || !email.trim() || !message.trim()}>
        {sending ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" /> Sending…
          </>
        ) : (
          <>
            <Send className="h-4 w-4" /> Send message
          </>
        )}
      </Button>
    </form>
  );
}
