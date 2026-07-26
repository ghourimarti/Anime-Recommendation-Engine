import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Cookie policy — ANIMA",
  description: "The cookies ANIMA sets and why.",
};

// TODO: legal review — realistic placeholder text; not reviewed by counsel.

export default function CookiesPage() {
  return (
    <>
      <h1>Cookie policy</h1>
      <p>Last updated: July 2026. Working draft pending legal review.</p>

      <h2>Cookies we set</h2>
      <ul>
        <li><strong>Session cookies</strong> — set by our sign-in provider (Clerk) to keep you signed in. Strictly necessary; the product cannot work without them.</li>
        <li><strong>Preference cookies</strong> — none currently; the interface has a single theme.</li>
      </ul>

      <h2>Cookies we don&apos;t set</h2>
      <ul>
        <li>No advertising or cross-site tracking cookies.</li>
        <li>No third-party analytics cookies.</li>
      </ul>

      <h2>Managing cookies</h2>
      <p>Blocking the session cookie in your browser will sign you out. Everything else on the site works without optional cookies because we don&apos;t set any.</p>
    </>
  );
}
