// Anime metadata proxy (UI redesign). Resolves a MyAnimeList id → cover art +
// real MAL metadata (community score, genres, episodes, year) via the public
// Jikan API (the MAL REST API; no key required).
//
// Why a server route and not a direct browser fetch to Jikan:
//   1. Jikan rate-limits per IP (3 req/s, 60/min). Fronting it with Next's data
//      cache (revalidate below) collapses thousands of users into ONE upstream
//      hit per anime per week — this metadata is effectively static.
//   2. Keeps the client ignorant of the upstream; swapping to TMDB or a
//      self-hosted store later touches only this file.
//
// Always returns 200 with the EMPTY shape on any failure (rate-limit, 404,
// network) so the client renders themed fallbacks instead of an error — missing
// metadata must never break a recommendation card.

import type { AnimeMeta } from "@/lib/types";

interface JikanImages {
  jpg?: { large_image_url?: string };
  webp?: { large_image_url?: string };
}

interface JikanAnime {
  images?: JikanImages;
  title?: string;
  score?: number;
  episodes?: number;
  year?: number;
  genres?: Array<{ name?: string }>;
  aired?: { prop?: { from?: { year?: number } } };
}

const EMPTY: AnimeMeta = {
  imageUrl: null,
  title: null,
  score: null,
  genres: [],
  episodes: null,
  year: null,
};

const ONE_WEEK_SECONDS = 604_800;

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ malId: string }> },
): Promise<Response> {
  const { malId } = await params;
  const id = Number(malId);
  if (!Number.isInteger(id) || id <= 0) {
    return Response.json(EMPTY, { status: 400 });
  }

  try {
    const upstream = await fetch(`https://api.jikan.moe/v4/anime/${id}`, {
      headers: { Accept: "application/json" },
      // Next data cache: one upstream fetch per anime per week, shared across
      // all users. The single biggest reason to proxy rather than fetch direct.
      next: { revalidate: ONE_WEEK_SECONDS },
    });
    if (!upstream.ok) {
      return Response.json(EMPTY);
    }
    const body = (await upstream.json()) as { data?: JikanAnime };
    const d = body.data;
    const meta: AnimeMeta = {
      imageUrl: d?.images?.webp?.large_image_url ?? d?.images?.jpg?.large_image_url ?? null,
      title: d?.title ?? null,
      score: typeof d?.score === "number" ? d.score : null,
      genres: Array.isArray(d?.genres)
        ? d.genres.map((g) => g.name).filter((n): n is string => Boolean(n))
        : [],
      episodes: typeof d?.episodes === "number" ? d.episodes : null,
      year:
        typeof d?.year === "number" ? d.year : (d?.aired?.prop?.from?.year ?? null),
    };
    return Response.json(meta, {
      headers: { "Cache-Control": "public, max-age=86400, stale-while-revalidate=604800" },
    });
  } catch {
    return Response.json(EMPTY);
  }
}
