import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge Tailwind class strings, de-duplicating conflicting utilities.
 * The shadcn/ui convention used by every UI primitive in this app. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
