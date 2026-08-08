# 00 — Baseline: Discovery & Regression Checklist

> UI Transformation workstream, Phase 0. Written 2026-07-11 against `main` @ `fd64ed4`.
> **Read this first:** unlike a typical "functional but unstyled" starting point, this app has
> already received a deliberate design pass in prior sessions (commits `18f3e00`, `ef3b515`:
> poster art, app shell, hero, ⌘K palette, motion system, "Cinematic Noir" theme, ANIMA brand).
> The gap to "launchable commercial product" is **not** visual identity — it's **commercial
> completeness**: marketing pages, pricing/subscriptions, account area, legal, footer anatomy.

---

## 1. Tech stack summary

| Layer | Choice | Notes |
|---|---|---|
| Framework | Next.js 15 (App Router), React 19, TypeScript 5.7 | Server Components + client islands |
| Styling | Tailwind CSS 3.4 + shadcn/ui-style tokens (CSS variables, HSL triplets) | `tailwindcss-animate`; tokens in `globals.css` |
| Motion | framer-motion 12 (`MotionProvider`, `Reveal`, `StaggerList`) | respects `prefers-reduced-motion` (CSS + provider) |
| Fonts | next/font self-hosted: Instrument Serif (display), Inter (body), JetBrains Mono (data) | zero-CLS, CSS variables `--font-display/sans/mono` |
| Auth | Clerk (`@clerk/nextjs` 6) — middleware-gated, BFF token pattern | `middleware.ts` protects ALL routes except sign-in/up |
| State | Local React state + custom hooks; **no** global store | `use-recommend.ts` (SSE), `use-anime-meta.ts` (posters) |
| Data | BFF: browser → same-origin `/api/*` route handlers → FastAPI backend with server-minted Clerk JWT | `lib/proxy.ts`; `API_BASE_URL` never reaches the client |
| Icons | lucide-react | consistent set |
| Toast | sonner (dark theme) | degraded-notice + error surfaces |
| Command menu | cmdk | ⌘K palette |
| Tests | Vitest (unit ×4 files), Playwright (e2e recommend flow) | 13+ unit tests |
| Build | next build (standalone-ready), pnpm | Dockerfile exists (`infra/compose/docker-compose.app.yml`) |

## 2. Route map (current)

| Path | Type | Auth | Purpose |
|---|---|---|---|
| `/` | Server page + client island | **required** (middleware redirect) | The product: query → 3 recommendations → streamed explanation |
| `/history` | Server Component (`force-dynamic`) | required | "Your Watchlist" — past queries + cards |
| `/sign-in/[[...sign-in]]` | Clerk widget | public | Sign-in |
| `/sign-up/[[...sign-up]]` | Clerk widget | public | Sign-up |
| `/api/recommend` | Route handler (BFF) | required | Proxy → `POST /v1/recommend` (forwards 429 + Retry-After) |
| `/api/recommend/stream` | Route handler (BFF, streams) | required | Proxy → SSE `POST /v1/recommend/stream` |
| `/api/feedback` | Route handler (BFF) | required | Proxy → `POST /v1/feedback` |
| `/api/history` | Route handler (BFF) | required | Proxy → `GET /v1/history` |
| `/api/poster/[malId]` | Route handler | required | Jikan poster proxy + cache (next/image source) |
| `opengraph-image.tsx`, `icon.svg` | Metadata routes | public | OG card + favicon |

**No** marketing, pricing, account, legal, 404/500-branded, about/contact/help routes exist.

## 3. Component inventory

**Shared UI primitives** (`components/ui/`): `button` (CVA variants), `card`, `skeleton`, `textarea`.

**Feature components:**

| Component | Used by | Client? | Coupling risk |
|---|---|---|---|
| `query-experience.tsx` | `/` | ✓ | **HIGH** — the state machine (loading/error/quota/result) is inline with markup |
| `recommendation-card.tsx` | `/`, `/history` | ✓ | MED — frozen props: `rec, queryHistoryId, rank, priority, showFeedback` |
| `streaming-explanation.tsx` | `/` | ✓ | MED — consumes `use-recommend` hook |
| `feedback-buttons.tsx` | rec card | ✓ | MED — POST handler attached |
| `quota-notice.tsx` | `/` | ✓ | LOW — display + countdown |
| `command-palette.tsx` | layout header | ✓ | MED — global key listener, router pushes, `/?q=` contract |
| `poster.tsx` + `lib/poster-fallback.ts` | rec card | ✓ | LOW — next/image + fallback art |
| `reveal.tsx`, `motion-provider.tsx` | everywhere | ✓ | LOW — presentation only |
| `layout.tsx` header/footer | all pages | server | LOW — will be replaced by app-shell work (3B) |

**Libraries (`lib/`):** `proxy.ts` (frozen), `sse.ts` (frozen), `use-recommend.ts` (frozen), `types.ts` (frozen contracts), `examples.ts`, `format.ts`, `use-anime-meta.ts`, `utils.ts` (cn).

## 4. Current styling system ("Cinematic Noir / Marquee Amber")

Already implemented in `globals.css` + `tailwind.config.ts`:

- **Palette:** near-black ink `#0B0B0F` base → charcoal panels `#141419` / `#1C1C24`; text `#F4F4F5`/`#A1A1AA`; hairline `#2A2A33`; **one accent: Marquee Amber `#E8B339`** (CTAs, match-score, focus ring only).
- **Type:** Instrument Serif for page-level h1/h2 (editorial), Inter body, JetBrains Mono for data/kbd.
- **Signature elements:** film-grain noise overlay (fixed, 3.5% opacity), amber spotlight radial bleeding from the top, glow-on-focus query box.
- **Dark-only** (`.dark` forced on `<html>`; no light theme — per guardrails, do not build one).
- Radius 0.75rem; motion via framer-motion with reduced-motion kill switch.

## 5. Regression checklist (re-verify each in Phase 4)

Every item independently checkable. **All currently pass.**

| # | Behavior | How to check |
|---|---|---|
| R1 | Unauthenticated visit to `/` or `/history` → 307 redirect to `/sign-in` | curl -I or browser incognito |
| R2 | `/sign-in` + `/sign-up` render Clerk widgets, complete a session | browser |
| R3 | Signed-in `/` renders hero, textarea, example chips, submit button | browser |
| R4 | Clicking an example chip fills the textarea | browser |
| R5 | ⌘/Ctrl+Enter in textarea submits | browser |
| R6 | Submit → POST `/api/recommend` → exactly 3 recommendation cards (title, summary, why-match, rank badge, poster) | browser + network tab |
| R7 | While loading: 3 skeleton cards render | throttle network |
| R8 | 429 from backend → QuotaNotice with Retry-After countdown (no crash) | exhaust quota or stub |
| R9 | Network error → error card with working "Try again" | kill API |
| R10 | Degraded response (`degraded:true`) → sonner warning toast with notice text | kill LLM (LLM_ENABLED=false) |
| R11 | Posters load via `/api/poster/[malId]`; fallback art when Jikan misses | browser |
| R12 | "Explain these picks" streams tokens incrementally (SSE), not one blob | browser, watch text grow |
| R13 | Stop button aborts the stream mid-flight (status → done, no error) | browser |
| R14 | Thumbs up/down → POST `/api/feedback` → visual confirmation, no dup submits | browser + network tab |
| R15 | `/history` lists past queries with cards; feedback hidden (`showFeedback=false`) | browser |
| R16 | `/history` empty state: clapperboard icon + "Find anime" CTA → `/` | fresh account |
| R17 | ⌘K opens palette; Esc + backdrop click close; nav items route | browser |
| R18 | Palette example prompt → `/?q=…` → textarea prefilled | browser |
| R19 | `?q=` deep link prefills the query box (shareable) | paste URL |
| R20 | Clerk UserButton renders; sign-out returns to `/sign-in` | browser |
| R21 | OG image renders (social card), favicon present | /opengraph-image |
| R22 | `prefers-reduced-motion` disables reveals/stagger animations | OS setting or devtools emulation |
| R23 | `pnpm typecheck && pnpm test && pnpm lint` all clean | terminal |
| R24 | Playwright e2e recommend flow passes | `pnpm test:e2e` |

## 6. Risk register (where restyling can break logic)

| Risk | File | Mitigation |
|---|---|---|
| **Middleware matcher**: every NEW public page (landing, pricing, legal…) must be added to `isPublicRoute` or it 307s to sign-in. Conversely a typo could expose `/history`. | `middleware.ts` | Explicit matcher review + R1 recheck after every new route |
| Inline state machine in the main page component — restructuring markup can orphan a state branch (quota/error/result are `!loading &&` chained) | `query-experience.tsx` | Preserve all conditional branches verbatim; restyle inside them |
| SSE stream consumption — any wrapper that buffers the response body kills token streaming | `app/api/recommend/stream/route.ts`, `use-recommend.ts` | Do not touch; presentation changes live in `streaming-explanation.tsx` only |
| Frozen card props consumed from two pages with different flags | `recommendation-card.tsx` | Keep prop surface identical |
| Global ⌘K listener + `/?q=` contract — new pages must not re-register the hotkey or shadow the search param | `command-palette.tsx` | One palette instance in the shell only |
| `layout.tsx` will be significantly restructured (3B app shell + footer) — it wraps EVERYTHING; Clerk provider order & `suppressHydrationWarning` must survive | `layout.tsx` | ClerkProvider stays outermost; test R2/R20 after |
| Server-fetch on history page — moving it into a client component would put the Clerk token path in the browser | `history/page.tsx` | Keep as Server Component |

## 7. What's missing vs. "launchable commercial product" (drives Phase 3 scope)

1. Marketing landing (currently `/` is the app, gated behind auth — a stranger sees a sign-in wall)
2. Features page · Pricing page (3 tiers + toggle + comparison + FAQ) · subscription flow UI (stubbed billing)
3. Account/settings area + subscription management screen
4. About · Contact · Help/FAQ
5. Legal: Privacy / Terms / Cookies
6. Branded 404 + 500
7. Multi-column footer (current footer is a single row)
8. Per-page SEO meta beyond the root layout defaults
