/** Format a remaining-seconds count into a compact human countdown.
 *  > 1h  → "2h 5m"  ·  > 1m → "4m 12s"  ·  else → "45s"  ·  clamps negatives. */
export function formatCountdown(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const hours = Math.floor(s / 3600);
  const minutes = Math.floor((s % 3600) / 60);
  const seconds = s % 60;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${seconds}s`;
  return `${seconds}s`;
}
