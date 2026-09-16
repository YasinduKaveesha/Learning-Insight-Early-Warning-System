import type { ReactNode } from "react";

/**
 * Skeleton building blocks (2026-09-16).
 *
 * A skeleton screen is a grey outline of the page that is about to appear: the same cards in
 * the same places, so the real content drops in without the page jumping. Every page has its
 * own, built from these two pieces (see `PageSkeletons.tsx`).
 *
 * Two rules, both tested:
 * - **No text and no numbers.** A placeholder "0" or "Loading name…" would put a figure on a
 *   teacher's screen that did not come from the API, which this app never does.
 * - **Movement only for people who allow it.** The pulse is `motion-safe:` -- anyone who has
 *   asked their device to reduce motion gets still grey shapes.
 */

/** One grey shape. Size and roundness come from the caller, so a bone can be a line of text,
 * a number, a pill button or a whole card. */
export function Bone({ className = "" }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      data-skeleton-bone=""
      className={`rounded-md bg-surface3 motion-safe:animate-pulse ${className}`}
    />
  );
}

/** The one element a screen reader hears while a page loads. Everything inside is hidden
 * from assistive technology, so it announces "Loading class" once rather than forty shapes. */
export function SkeletonRegion({
  label,
  className = "",
  children,
}: {
  label: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div role="status" aria-label={label} aria-busy="true" className={className}>
      {children}
    </div>
  );
}
