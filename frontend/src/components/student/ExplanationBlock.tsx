export interface ExplanationBlockProps {
  /** Already ≤280 chars, filtered, display-names-only from the API/mock
   * client (lib/presentation.ts's filterExplanation). This component does
   * not re-derive or re-map anything — it renders what it is given. */
  explanation: string | null;
}

/** A suppressed or null explanation renders nothing — not an empty "Why?"
 * heading (a heading with nothing under it reads as a broken page, not as
 * "there is no reason"). */
export function ExplanationBlock({ explanation }: ExplanationBlockProps) {
  if (!explanation) return null;
  return (
    <div>
      <h3 className="text-sm font-semibold text-ink-primary">Why?</h3>
      <p className="mt-1 text-sm text-ink-primary">{explanation}</p>
    </div>
  );
}
