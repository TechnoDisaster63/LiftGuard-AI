import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Standard shadcn utility: merges clsx-resolved class lists through
 * tailwind-merge so conflicting Tailwind classes (e.g. two different
 * `px-*` values from a base + override) resolve to the last one instead
 * of both landing in the DOM.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
