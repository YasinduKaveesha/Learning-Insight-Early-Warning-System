export interface ExplanationBlockProps {
  /** Already ≤280 chars, filtered, display-names-only from the API/mock
   * client (lib/presentation.ts's filterExplanation). This component does
   * not re-derive or re-map anything — it renders what it is given. */
  explanation: string | null;
  /** UI-refinement pass: the watch-list card opts out of the "Why?"
   * heading (default true keeps every other caller — Student Overview,
   * the gallery — unchanged). */
  showHeading?: boolean;
  /** UI-refinement pass: caps the explanation at N lines (Tailwind
   * line-clamp) so cards of varying explanation length come out the same
   * height — used by the /watch list cards. Undefined (default, every
   * other caller) renders the full text, unclamped — the explanation is
   * still never behind a tap, just visually capped where a caller opts in. */
  clampLines?: number;
}

/** A suppressed or null explanation renders nothing — not an empty "Why?"
 * heading (a heading with nothing under it reads as a broken page, not as
 * "there is no reason"). */
export function ExplanationBlock({ explanation, showHeading = true, clampLines }: ExplanationBlockProps) {
  if (!explanation) return null;
  return (
    <div>
      {showHeading ? <h3 className="text-sm font-semibold text-ink-primary">Why?</h3> : null}
      <p
        className="mt-1 text-sm text-ink-primary"
        style={clampLines ? { display: "-webkit-box", WebkitLineClamp: clampLines, WebkitBoxOrient: "vertical", overflow: "hidden" } : undefined}
      >
        {explanation}
      </p>
    </div>
  );
}
