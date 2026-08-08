# 02 — Design Direction Proposal (APPROVAL GATE)

> UI Transformation workstream, Phase 2. Written 2026-07-11. **No implementation code until sign-off.**
> Honest context: prior sessions already shipped a partial identity ("Cinematic Noir / Marquee
> Amber", ANIMA brand — commits `18f3e00`, `ef3b515`). Direction A below is that identity,
> completed and codified. Direction B is a genuine alternative, not a strawman. The decision is
> therefore *evolve vs. replace* — and replacement costs re-doing two shipped UI phases.

---

## Direction A — "Cinematic Noir" (evolve the shipped identity)

**Concept:** a film premiere, not a database. Near-black auditorium surfaces, one amber
"marquee" light source, editorial serif headlines, film-grain texture. The product moment —
typing what you feel like watching — is staged like a spotlight hitting the screen.

**Palette (6 named values):**

| Name | Hex | Role |
|---|---|---|
| Ink | `#0B0B0F` | app base |
| Panel | `#141419` | elevated cards |
| Surface-2 | `#1C1C24` | hovers, secondary chrome |
| Hairline | `#2A2A33` | borders |
| **Marquee Amber** | `#E8B339` | THE accent — CTAs, match score, focus, brand mark |
| Screen White | `#F4F4F5` | primary text |

**Typography pairing:** Instrument Serif (display — headlines only, used with restraint) ·
Inter (body/UI) · JetBrains Mono (data: scores, kbd hints, timestamps). *Already self-hosted via next/font.*

**Layout concept:** one-column theatrical stage — generous vertical rhythm, content never wider
than the "screen" (max-w-2xl app / max-w-6xl marketing), posters as the only imagery.

**Landing hero (ASCII):**

```
┌──────────────────────────────────────────────────────────────┐
│  ◆ ANIMA                      Features  Pricing  [Sign in]   │
│                                                              │
│            ~ amber spotlight bleeds from top ~               │
│                                                              │
│        Stop scrolling lists.                                 │
│        Say what you feel like watching.        ← serif, 64px │
│                                                              │
│   ┌────────────────────────────────────────────────┐        │
│   │ "a slow-burn revenge story with a clever…"  ▊  │ ← LIVE │
│   └────────────────────────────────────────────────┘  query │
│         [ Get three picks — free ]                     box   │
│                                                              │
│      ┌──────┐   ┌──────┐   ┌──────┐                          │
│      │poster│   │poster│   │poster│  ← real picks, fanned    │
│      └──────┘   └──────┘   └──────┘                          │
└──────────────────────────────────────────────────────────────┘
```

**Motion language:** slow reveals (450ms ease-out), stagger on card lists, spotlight glow on
focus; nothing bounces. Page transitions = 200ms fade-through-black (cinema cut).
**Signature element:** the **film-grain + amber marquee light** — the query box literally glows
like a lit marquee when focused. Everything else stays quiet.

## Direction B — "After-Hours Broadcast" (the alternative)

**Concept:** late-night anime TV block / neon-city aesthetic. Deep indigo night, one neon-sakura
accent, CRT-glow interactive elements, grotesque display type. More energetic, more "fandom",
younger register.

**Palette:** Midnight `#070B14` · Panel `#10162A` · Hairline `#232B44` · **Neon Sakura
`#FF4D8F`** (accent) · Ghost Cyan `#59F3F3` (micro-accent, data only) · Signal White `#EEF1F8`.
**Typography:** Space Grotesk (display) · Inter (body) · IBM Plex Mono (data).
**Layout concept:** asymmetric two-column hero (copy left, live "broadcast card" right), denser grid for cards.

```
┌──────────────────────────────────────────────────────────────┐
│  ▲NIMA                        Features  Pricing  [Sign in]   │
│                                                              │
│   TONIGHT'S PICKS,            ┌─────────────────────┐        │
│   CHOSEN BY HOW               │  ⟩ scanline card    │        │
│   YOU FEEL.                   │  "cozy fantasy…" ▊  │        │
│                               │  → 3 picks · 4.2s   │        │
│   [ Start watching smarter ]  └─────────────────────┘        │
└──────────────────────────────────────────────────────────────┘
```

**Motion:** faster (150–250ms), glow pulses, subtle chromatic aberration on hover.
**Signature element:** CRT scanline sweep on the live demo card.

## Recommendation: **Direction A**

1. **Audit-grounded:** the market's only modern player (AniList) is *vibrant-dark-blue* —
   Direction B would swim toward AniList's register; Noir's restrained cinema register is the
   one nobody in the category owns. The premium gap identified in Phase 1 is exactly what A sells.
2. **Two UI phases of A are already shipped and tested.** Choosing B rewrites working, committed
   code for aesthetics — the "most expensive kind of rework" this gate exists to prevent.
3. **Anti-goal check:** A is not the near-black+acid-green AI-default (amber + grain + serif is a
   distinct, referenced language: cinema, not terminal), not cream+terracotta, not broadsheet.

## Route architecture decision — ⚠ NEEDS YOUR EXPLICIT SIGN-OFF

`/` is currently the authenticated app; signed-out visitors are redirected to `/sign-in` and
never see a product story. Options:

| | Option | Behavior change | Verdict |
|---|---|---|---|
| (a) | Marketing takes `/`; app moves to `/app` | **Repurposes an existing route** — breaks bookmarks, R-checklist, deep links | Not recommended |
| (b) | App keeps `/`; marketing at `/home` | Zero change, but strangers still hit a sign-in wall; marketing page orphaned | Weak |
| **(c)** | **Conditional root:** signed-out → marketing landing at `/`; signed-in → the app, exactly as today | Signed-in behavior identical (zero regression for users); **R1 semantics change**: signed-out `/` renders landing instead of redirecting (other routes still redirect) | **Recommended** — the Linear/Notion pattern |

Implementation of (c): `/` added to the public matcher in `middleware.ts`; the page Server
Component branches on `auth()`. `/history` etc. stay protected. R1 in the baseline checklist
gets amended accordingly (documented, not silent).

## Token specification (Direction A)

- **Color scale:** the 6 palette values above + semantic states — success `#34D399`, warning
  amber (reuse `#E8B339`), destructive `#EF4444` (existing), each with `/10` alpha surface tints.
  Already expressed as shadcn HSL variables in `globals.css`; Phase 3A only *extends* (adds
  success + marketing-surface tokens), never rewrites.
- **Type scale (rem):** display 4.0/1.05 · h1 2.5/1.15 · h2 2.0/1.2 · h3 1.5/1.3 · body 1.0/1.6
  · small 0.875/1.5 · micro 0.75/1.4 (mono). Serif for display/h1/h2 only.
- **Spacing:** Tailwind 4px base scale; section rhythm on marketing pages = 96px (24) desktop / 64px (16) mobile.
- **Radius:** sm 0.5rem · DEFAULT 0.75rem (shipped) · lg 1rem (marketing cards) · full (chips).
- **Elevation (3 steps):** card = ring-1 hairline; popover = shadow-lg + ring-1; modal = shadow-2xl + backdrop-blur + black/70 scrim.
- **Motion:** micro 150ms · UI 250ms · reveal 450ms; easing `cubic-bezier(0.22,1,0.36,1)`
  (ease-out-quart); `prefers-reduced-motion` kills all (already wired).

## Phase 3 scope under Direction A (preview, for sizing)

3A extend tokens → 3B app shell (nav with public/auth states, multi-column footer, mobile nav)
→ 3C restyle-in-place polish of `/`, `/history`, auth pages (already 90% there) → 3D **the bulk**:
landing (conditional root), `/features`, `/pricing` (Free $0 / Pro $4.99 / Premium $9.99, annual
−20%), checkout stub behind `NEXT_PUBLIC_BILLING_ENABLED=false`, `/account` (profile/preferences/
subscription), `/about`, `/contact`, `/help`, `/legal/{privacy,terms,cookies}`, branded
`not-found.tsx` + `error.tsx` → 3E polish (per-page meta, OG variants, focus states, transitions).

**Billing:** UI-complete, stubbed. I will NOT integrate Stripe or any provider without separate explicit confirmation.
