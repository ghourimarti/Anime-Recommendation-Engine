"use client";

import { useEffect, useState } from "react";

import type { AnimeMeta } from "@/lib/types";

const EMPTY: AnimeMeta = {
  imageUrl: null,
  title: null,
  score: null,
  genres: [],
  episodes: null,
  year: null,
};

// Module-level cache: a given mal_id → metadata is stable, so we resolve it once
// per session no matter how many cards (poster + meta row) read it. The card and
// its <Poster> both call this hook with the same id → one network fetch, deduped.
const cache = new Map<number, AnimeMeta>();

interface AnimeMetaState {
  meta: AnimeMeta;
  loading: boolean;
}

/** Resolve an anime's poster + real MAL metadata from the BFF poster route. */
export function useAnimeMeta(malId: number): AnimeMetaState {
  const [state, setState] = useState<AnimeMetaState>(() =>
    cache.has(malId)
      ? { meta: cache.get(malId) ?? EMPTY, loading: false }
      : { meta: EMPTY, loading: true },
  );

  useEffect(() => {
    if (cache.has(malId)) {
      setState({ meta: cache.get(malId) ?? EMPTY, loading: false });
      return;
    }
    let active = true;
    const controller = new AbortController();
    (async () => {
      try {
        const res = await fetch(`/api/poster/${malId}`, { signal: controller.signal });
        const data = (await res.json()) as Partial<AnimeMeta>;
        const meta: AnimeMeta = { ...EMPTY, ...data };
        cache.set(malId, meta);
        if (active) setState({ meta, loading: false });
      } catch {
        // Abort on unmount, or a network error → render fallbacks.
        if (active) setState({ meta: EMPTY, loading: false });
      }
    })();
    return () => {
      active = false;
      controller.abort();
    };
  }, [malId]);

  return state;
}
