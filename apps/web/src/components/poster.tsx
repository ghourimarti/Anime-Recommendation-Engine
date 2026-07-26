"use client";

import Image from "next/image";

import { posterGradient, posterInitial } from "@/lib/poster-fallback";
import { useAnimeMeta } from "@/lib/use-anime-meta";
import { cn } from "@/lib/utils";

interface PosterProps {
  malId: number;
  title: string;
  className?: string;
  /** Eager-load the first poster above the fold (LCP); lazy-load the rest. */
  priority?: boolean;
  /** Fill the parent's height instead of enforcing the 2:3 ratio (for the
   *  horizontal card, where the poster stretches to the content height). */
  fill?: boolean;
}

/** Anime cover art. Three states: skeleton while resolving, the real image when
 *  found, a themed gradient + initial otherwise. */
export function Poster({ malId, title, className, priority, fill = false }: PosterProps) {
  const { meta, loading } = useAnimeMeta(malId);
  const imageUrl = meta.imageUrl;

  return (
    <div
      className={cn(
        "relative overflow-hidden bg-secondary",
        !fill && "aspect-[2/3]",
        className,
      )}
    >
      {loading ? (
        <div className="absolute inset-0 animate-pulse bg-secondary" />
      ) : imageUrl ? (
        <Image
          src={imageUrl}
          alt={`${title} cover art`}
          fill
          sizes="(max-width: 768px) 33vw, 200px"
          className="object-cover transition-transform duration-500 group-hover:scale-105"
          priority={priority}
        />
      ) : (
        <div
          className="absolute inset-0 flex items-center justify-center"
          style={{ backgroundImage: posterGradient(title) }}
          aria-label={`${title} (no cover art)`}
        >
          <span className="font-display text-4xl text-foreground/30">
            {posterInitial(title)}
          </span>
        </div>
      )}
    </div>
  );
}
