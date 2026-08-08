# 03 — Final Report: Enterprise UI Transformation

> UI Transformation workstream, Phases 3–4. Written 2026-07-11.
> Scope executed: Direction A ("Cinematic Noir"), route option (c) (conditional root) — both user-approved.

---

## 1. Route map — before → after

| Route | Before | After |
|---|---|---|
| `/` | App, auth-required (strangers → sign-in wall) | **Conditional**: signed-out → marketing landing (public) · signed-in → app **unchanged** |
| `/history` | App, auth-required | Unchanged |
| `/sign-in`, `/sign-up` | Public Clerk pages | Unchanged |
| `/api/*` (5 BFF routes) | Auth-required | Unchanged (incl. `/api/poster` — deliberately NOT public) |
| `/features` | — | **NEW** public: per-feature deep page (6 real capabilities) |
| `/pricing` | — | **NEW** public: 3 tiers, monthly/annual toggle (−20%), comparison table, FAQ |
| `/checkout` | — | **NEW** auth-required: order summary + payment UI **stubbed** behind `NEXT_PUBLIC_BILLING_ENABLED=false` |
| `/account` | — | **NEW** auth-required: profile, subscription (Free-plan state), invoices placeholder, preferences |
| `/about`, `/contact`, `/help` | — | **NEW** public (contact form UI works; submission stubbed — no backend endpoint exists) |
| `/legal/privacy`, `/legal/terms`, `/legal/cookies` | — | **NEW** public, shared legal layout, `TODO: legal review` marked |
| 404 / 500 | Next.js defaults | **NEW** branded `not-found.tsx` + `error.tsx` (with working `reset()`) |

## 2. Everything changed (existing files)

| File | Change | Risk class |
|---|---|---|
| `middleware.ts` | Public matcher extended: `/`, marketing routes, legal. `/account`, `/checkout`, `/history`, `/api/*` remain protected | **Auth boundary — reviewed twice, smoke-tested** |
| `app/page.tsx` | Branches on `auth()`: signed-out → `<Landing/>`, signed-in → identical `<QueryExperience/>` (now `force-dynamic`) | Behavior addition, not change, for signed-in |
| `app/layout.tsx` | Inline header/footer swapped for `<SiteHeader/>`/`<SiteFooter/>`; flex column body so footer sits at viewport bottom. ClerkProvider position untouched | Presentation |
| `globals.css` | +`--success` tokens | Additive |
| `tailwind.config.ts` | +`success` color, +`rounded-xl` (also: `require`→ESM import, pre-existing fix) | Additive |
| `UserButton afterSignOutUrl` | `/sign-in` → `/` (sign-out now lands on the marketing page — friendlier exit; sign-in remains one click) | Deliberate UX change, logged |
| `.env.example`, `apps/web/.env.local.example`, `apps/web/Dockerfile`, `infra/compose/docker-compose.app.yml` | `NEXT_PUBLIC_BILLING_ENABLED` plumbed as build-time flag (default `false`) | Infra, additive |

**Untouched (frozen contracts honored):** `proxy.ts`, `sse.ts`, `use-recommend.ts`, all 5 BFF route handlers, `query-experience.tsx`, `recommendation-card.tsx`, `streaming-explanation.tsx`, `feedback-buttons.tsx`, `command-palette.tsx`, history page, all types. **Zero new dependencies.**

## 3. Everything added (new files)

`components/shell/`: `site-header.tsx`, `site-footer.tsx`, `mobile-nav.tsx` ·
`components/marketing/`: `landing.tsx`, `pricing-table.tsx`, `contact-form.tsx` ·
`app/`: `features/`, `pricing/`, `checkout/`, `account/`, `about/`, `contact/`, `help/`,
`legal/{layout,privacy,terms,cookies}`, `not-found.tsx`, `error.tsx` — every page exports its own `metadata` (title + description).

## 4. Verification record

**Machine-verifiable (all run, all green):**

| Check | Result |
|---|---|
| `pnpm typecheck` | ✅ clean |
| `pnpm lint` | ✅ clean (after fixing 2 unescaped apostrophes) |
| `pnpm test` | ✅ 23/23 unit tests |
| `pnpm build` | ✅ 22 routes compile; First Load JS 102–150 kB |
| Prod-server smoke (`pnpm start`) | ✅ signed-out `/` → 200 + landing copy · `/history` → 307 to sign-in · `/account` → 307 · `/pricing` → 200 + tiers · `/legal/privacy` → 200 · `/legal/nonexistent` → **404 branded page** |

**Needs a live browser session (your part — signed-in flows can't be curl'd):**
R2–R22 of the baseline checklist (sign-in, submit query, skeletons, quota notice, degraded toast, posters, streaming + stop, feedback, history, ⌘K, `?q=` prefill, sign-out) plus responsive spot-checks at 360/768/1024/1440 and Lighthouse runs. The signed-in surface itself was **not modified** (frozen files above), so the regression risk concentrates in: middleware matcher, layout swap, and sign-out landing — R2, R3, R17, R20 are the ones to check first.

**R1 amended as approved:** signed-out `/` now renders the landing (200) instead of redirecting; all other app routes still 307. This was the explicit route-option-(c) sign-off.

## 5. Safety compromises (logged per brief §8)

1. **Unknown non-public paths 307 to sign-in instead of showing the branded 404** (e.g. `/nonexistent`). Cause: Clerk middleware fails closed — anything not in the public matcher requires auth, including paths that don't exist. Chosen deliberately: fail-closed means a typo'd future app route can never leak content. The branded 404 renders wherever the middleware allows (signed-in users everywhere; strangers under public patterns like `/legal/*`, `/pricing/*`). Alternative (enumerate-and-allow unknown paths) would invert the security default — rejected.
2. **No page transitions** (3E item): App Router + framer-motion route transitions require wrapping route content in client components with exit-animation state — measurable regression risk against streaming SSE pages for a cosmetic gain. Skipped; micro-interactions + reveals retained.
3. **Contact form delivery is stubbed** and says so in the toast ("delivery in preview during the beta") — honest-placeholder policy over fake success.

## 6. Known TODOs

- `TODO: legal review` — all three legal pages are working drafts.
- `TODO: replace with real testimonials` — landing quotes are clearly-marked placeholders.
- `TODO: integrate payment provider` — checkout is UI-complete, stubbed; **requires your explicit approval** before any Stripe/provider work.
- `TODO: wire contact form` to a real endpoint or support inbox.
- Playwright e2e for the new marketing routes (existing recommend-flow spec untouched and still valid).
- Lighthouse ≥90 validation — run against a deployed/production build with real Clerk keys.

## 7. Definition-of-done status

| Criterion | Status |
|---|---|
| Regression checklist 100% | Machine-verifiable items pass; browser items pending your session (signed-in surface untouched) |
| "Stranger would believe it's a funded commercial product" | Landing + features + pricing + legal + branded errors now exist; judge on `make dev-web` signed-out |
| Four docs delivered | ✅ 00-baseline · 01-competitor-audit · 02-design-direction · 03-final-report |
