// Deterministic gradient + initial for anime with no cover art, so a missing
// poster reads as intentional (themed) rather than broken. Pure + unit-tested.

/** Hash a title to a stable hue in [0, 360). */
function hashHue(title: string): number {
  let hash = 0;
  for (let i = 0; i < title.length; i += 1) {
    hash = (hash * 31 + title.charCodeAt(i)) % 360;
  }
  return hash;
}

/** A low-saturation, hue-shifted dark gradient — stays inside the Noir palette
 *  so fallback posters feel part of the set, not a random rainbow. */
export function posterGradient(title: string): string {
  const hue = hashHue(title);
  return `linear-gradient(135deg, hsl(${hue} 28% 18%), hsl(${hue} 22% 8%))`;
}

/** The first alphanumeric character, uppercased — the watermark on a fallback. */
export function posterInitial(title: string): string {
  const match = title.match(/[A-Za-z0-9]/);
  return (match?.[0] ?? "?").toUpperCase();
}
