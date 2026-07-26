import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Terms of service — ANIMA",
  description: "The agreement for using ANIMA.",
};

// TODO: legal review — realistic placeholder text; not reviewed by counsel.

export default function TermsPage() {
  return (
    <>
      <h1>Terms of service</h1>
      <p>Last updated: July 2026. Working draft pending legal review.</p>

      <h2>The service</h2>
      <p>ANIMA provides AI-assisted anime recommendations. Recommendations are grounded in a real catalog but are suggestions, not guarantees of enjoyment — taste remains yours.</p>

      <h2>Your account</h2>
      <p>You are responsible for activity under your account. One account per person; don&apos;t share credentials or automate requests against the service outside documented interfaces.</p>

      <h2>Fair use</h2>
      <p>Plan limits (asks per day) exist to keep the service fast and affordable for everyone. Circumventing limits, scraping, or reselling access may lead to suspension.</p>

      <h2>Paid plans</h2>
      <p>When billing is live: subscriptions renew until cancelled; cancellation stops the next renewal and paid features remain until the period ends. Pricing changes are announced in advance.</p>

      <h2>Content and IP</h2>
      <p>Anime titles, artwork, and metadata belong to their respective rights holders. ANIMA&apos;s recommendations, explanations, and interface are ours; your queries and feedback remain yours, licensed to us to operate the service.</p>

      <h2>Warranty and liability</h2>
      <p>The service is provided “as is” without warranties; to the extent permitted by law our liability is limited to the amount you paid in the preceding twelve months.</p>

      <h2>Changes</h2>
      <p>We may update these terms; material changes will be announced in-product with reasonable notice.</p>
    </>
  );
}
