# 01 — Competitor Audit

> UI Transformation workstream, Phase 1. Written 2026-07-11.
> **Method + confidence:** MyAnimeList was fetched directly (full confidence). AniList,
> Anime-Planet, Kitsu, and AniDB block automated fetches (HTTP 403) — those audits are built
> from search-result synthesis (reviews, comparisons, official forum/Patreon pages) and carry
> **reduced confidence**, noted per row. Similarity formula (fixed, per brief):
> **Similarity % = 0.50·feature + 0.20·audience + 0.15·content-domain + 0.15·monetization** (sub-scores 0–100).

## Our app, for reference

**ANIMA** — natural-language, mood-based anime discovery. Describe a vibe → three grounded picks
with visible reasoning → streamed explanation → thumbs feedback → watch history. Freemium quota
(20/day free) with subscription tier planned. No database browsing, no community, no manga, anime-only.

---

## Verdict table

| Competitor | Similarity % | Classification | Est. scale | Confidence | Top 3 takeaways |
|---|---|---|---|---|---|
| **Anime-Planet** | **59%** | Partial | "millions of fans" (self-reported) | Reduced (403) | ① Closest functional overlap — recommendations are its core loop. ② Rec quality framed as a flywheel: "the more you log, the better the suggestions" — great narrative to borrow. ③ Ad-supported + comfort-perk supporter tier shows recs alone can anchor a business. |
| **MyAnimeList** | **53%** | Partial | ~4M+ members; largest in category | **Full (fetched)** | ① The incumbent: unmatched DB depth + community network effects. ② Reads as a 2010s community wiki — dense tables, banner ads, no premium design language. ③ Acquired by Gaudiy (May 2025) → user exodus in progress = market instability we can exploit. |
| **AniList** | **53%** | Partial | Largest MAL-exodus beneficiary; traffic climbing | Reduced (403) | ① The design benchmark of the category: dark-mode-native, customizable, modern SPA. ② Still list/database-first — discovery is filters, not language. ③ Donation-tier monetization only; no real premium product motion. |
| **Kitsu** | **46%** | Partial | Declining; apps delisted 2024, dev stalled early 2025 | Reduced (403) | ① Cautionary tale: "modern MAL alternative" that overreached on social. ② Stripe/PRO code removed — monetization retreat. ③ Its orphaned users are reachable. |
| **AniDB** | **31%** | Adjacent | Niche archivist community; ~$240/mo Patreon-funded | Reduced (403) | ① Not a competitor — a data utility (episode-level metadata, file renaming). ② The extreme end of database-era UI ("kind of outdated" is the consensus phrasing). ③ Reminder that depth ≠ product. |

**Sub-score arithmetic** (one line each):
- Anime-Planet: feature 50 (recs are its core, but it also carries DB/streaming/manga we don't) · audience 80 · domain 80 · monetization 40 → 25+16+12+6 = **59**.
- MyAnimeList: feature 35 (recs + watch-tracking overlap; 80% of MAL's surface has no ANIMA counterpart) · audience 85 · domain 80 · monetization 40 → **52.5 ≈ 53**.
- AniList: feature 35 (list-first tracking vs our recommendation-first) · audience 85 (most design-sensitive users = ours) · domain 80 · monetization 45 → **53**.
- Kitsu: feature 30 · audience 70 · domain 80 · monetization 30 → **45.5 ≈ 46**.
- AniDB: feature 15 (no NL recs at all) · audience 40 (archivists ≠ "what should I watch tonight") · domain 80 · monetization 20 → **30.5 ≈ 31**.

## Feature-overlap matrix

| Feature | MAL | AniList | A-Planet | Kitsu | AniDB | **ANIMA** |
|---|---|---|---|---|---|---|
| Anime database browsing | ● | ● | ● | ● | ● | — |
| Personal lists / status tracking | ● | ● | ● | ● | ● | ◐ (query history "Watchlist") |
| **NL / mood-based AI recommendations** | — | — | — | — | — | **●** |
| **Grounded "why this matches" reasoning** | — | — | — | — | — | **●** |
| Community rec engine | ◐ | ◐ | ● | ◐ | — | — |
| Community / forums / social | ● | ● | ● | ● | ◐ | — |
| Seasonal charts / rankings | ● | ● | ● | ◐ | ◐ | — |
| Legal streaming links | ◐ | ◐ | ● | ◐ | — | — |
| Manga coverage | ● | ● | ● | ● | — | — |
| Streamed conversational explanation | — | — | — | — | — | **●** |
| Feedback loop on recommendations | ◐ | ◐ | ● | ◐ | ● (votes) | ● |
| Premium/subscription tier | ◐ supporter | ◐ donator | ◐ supporter | ✝ removed | — Patreon | ● (planned, product-native) |
| Modern premium design language | — | ◐ | — | ◐ | — | ● (in progress) |

## Strategic section

**The core lens confirmed:** every platform in this market carries database-era UI. MAL is a
2010s wiki; AniDB is a 2000s data tool; Anime-Planet is ad-cluttered; Kitsu is abandoned;
AniList is the only one that reads modern, and even it is a *database with good dark mode*, not
a premium product. **The market is a database-tool market; nobody sells a premium-product
experience.** That gap — combined with MAL's post-acquisition instability — is the opening.

### Differentiation opportunities (build on these)

1. **Language-first discovery as the product, not a feature.** Every competitor starts from a
   database you must browse; ANIMA starts from a sentence. "Describe a vibe" is a category-of-one
   interaction — make it the hero, literally.
2. **Reasoning as trust surface.** No competitor explains *why* a title matches you. Our grounded
   why-match + streamed explanation is the premium justification — foreground it in marketing.
3. **Speed-to-answer vs. browsing paralysis.** 3 picks in ~5 seconds vs. 20 minutes of list
   filtering. Frame pricing around saved decision time.
4. **Premium presentation in a wiki market.** Cinematic identity + commercial-site anatomy makes
   ANIMA *look* like the only paid-grade product in the category — which is the entire thesis
   of this redesign.
5. **Honest-AI posture as brand.** Degraded-mode notices, visible grounding, no fake certainty —
   turn the engineering honesty (D18/D21) into marketing copy no incumbent can claim.
6. **Subscription-native economics.** Competitors bolt donation tiers onto free products; ANIMA
   prices a metered capability (LLM cost per query) — a defensible free-tier/paid-tier boundary
   (20/day free ceiling already enforced server-side).
7. **MAL-exodus timing.** Post-acquisition churn is sending users to alternatives *right now*;
   AniList catches list-keepers, nobody catches "just tell me what to watch" users.

### Patterns worth adopting

- **AniList:** dark-native polish, poster-art-forward layouts, snappy search affordances (our ⌘K already matches).
- **Anime-Planet:** the flywheel narrative — "feedback makes your next picks better" (we have the thumbs data path).
- **MAL:** seasonal/trending as a future lightweight entry point for users who don't know what to ask.
- **All:** cover art is the emotional currency of the category — keep posters large and first-class.

### Patterns to explicitly avoid

- MAL/AniDB information-density tables and link-farms — the definitional anti-goal.
- Ad clutter (Anime-Planet's banner+video ads) — nothing erodes premium faster.
- Kitsu's everything-social overreach — we have no community; don't fake one.
- Burying the primary action below folds of chrome — the query box stays above the fold everywhere.
- Fandom-cliché styling (childish mascots, rainbow genre chips) — cinematic, not convention-booth.

**Sources:** [MyAnimeList](https://myanimelist.net/) (direct fetch) · [AniList vs MAL — Achriom](https://www.achriom.com/blog/anilist-vs-myanimelist/) · [MAL vs AniList vs Kitsu 2026 — Achriom](https://www.achriom.com/blog/myanimelist-vs-anilist-vs-kitsu/) · [Anime-Planet review](https://tsumino-blog.com/anime-planet-review/) · [Anime-Planet reviews — SaaSHub](https://www.saashub.com/anime-planet-reviews) · [Kitsu vs MAL — Achriom](https://www.achriom.com/blog/kitsu-vs-mal/) · [AniDB — AlternativeTo](https://alternativeto.net/software/anidb/about/) · [AniDB Patreon](https://www.patreon.com/AniDB/about)
