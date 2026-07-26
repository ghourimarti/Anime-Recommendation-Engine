// TS mirror of the FastAPI Pydantic wire schemas (apps/api/src/anime_api/schemas.py).
// Hand-kept in sync — a contract test (or an OpenAPI codegen later)
// can enforce this, but at this size manual mirroring is clearer than a codegen
// toolchain.

export interface RecommendationOut {
  mal_id: number;
  title: string;
  summary: string;
  why_match: string;
}

export interface RecommendResponse {
  query: string;
  query_history_id: number;
  recommendations: RecommendationOut[];
  degraded: boolean;
  notice: string | null;
}

export interface HistoryItem {
  id: number;
  query: string;
  recommendations: RecommendationOut[];
  created_at: string;
}

export interface HistoryResponse {
  items: HistoryItem[];
  limit: number;
  offset: number;
}

export interface FeedbackRequest {
  query_history_id?: number | null;
  mal_id: number;
  rating: 1 | -1;
}

export interface FeedbackResponse {
  id: number;
  status: string;
}

/** Normalized client-side error for a quota breach (HTTP 429 + Retry-After). */
export interface QuotaError {
  kind: "quota";
  retryAfterSeconds: number;
  message: string;
}

/** Anime metadata resolved from the Jikan poster proxy (UI redesign).
 *  `score`/`genres`/`episodes`/`year` are REAL MyAnimeList data — not a
 *  recommendation "match" signal (we don't surface that in the wire contract). */
export interface AnimeMeta {
  imageUrl: string | null;
  title: string | null;
  score: number | null;
  genres: string[];
  episodes: number | null;
  year: number | null;
}
