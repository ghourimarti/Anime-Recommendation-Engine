import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Privacy policy — ANIMA",
  description: "What ANIMA stores, why, and how to get it deleted.",
};

// TODO: legal review — realistic placeholder text; not reviewed by counsel.

export default function PrivacyPage() {
  return (
    <>
      <h1>Privacy policy</h1>
      <p>Last updated: July 2026. This is a plain-language summary of what we store and why. It is a working draft pending legal review.</p>

      <h2>What we collect</h2>
      <ul>
        <li>Account identity (name, email) — managed by our sign-in provider, Clerk.</li>
        <li>Your queries and the recommendations returned — so your Watchlist works.</li>
        <li>Thumbs feedback — to measure and improve recommendation quality.</li>
        <li>Usage counts (asks per day) — to enforce plan limits fairly.</li>
      </ul>

      <h2>What we don&apos;t do</h2>
      <ul>
        <li>We don&apos;t sell your data. To anyone. Ever.</li>
        <li>We don&apos;t use your queries to advertise to you.</li>
        <li>We don&apos;t store payment card details — payments (when live) are handled by a PCI-compliant provider.</li>
      </ul>

      <h2>Where processing happens</h2>
      <p>Recommendation generation uses third-party AI providers (currently Groq and OpenAI) as sub-processors; query text is sent to them to produce your picks, under agreements that prohibit training on your data. Infrastructure runs in the United States (us-east-1).</p>

      <h2>Your rights</h2>
      <p>You can request an export or deletion of everything we hold about you by writing from your account email via the contact page. Deletion covers account records, query history, and feedback, and is propagated to our sign-in provider.</p>

      <h2>Retention</h2>
      <p>Query history is kept while your account is active. Server logs are retained on a rolling window for reliability and security, with personal fields redacted at write time.</p>
    </>
  );
}
