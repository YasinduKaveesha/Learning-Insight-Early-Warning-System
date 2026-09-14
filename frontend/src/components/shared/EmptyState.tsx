export interface EmptyStateProps {
  /** Says what would fill it — e.g. "No students yet. Share the class key so students can join." */
  message: string;
  /** UI-refinement pass: "blue" matches the watch.watching card colour
   * (a solid rounded card instead of a dashed neutral box) — opt-in so
   * every other empty state (no classes, no sessions, ...) keeps its
   * original plain look. Used by Classroom's "Students to Watch" section. */
  tone?: "neutral" | "blue";
}

const TONE_CLASSES: Record<NonNullable<EmptyStateProps["tone"]>, string> = {
  neutral: "rounded-lg border border-dashed border-border-strong",
  blue: "rounded-lg border border-watch-watching-border bg-watch-watching-bg",
};

export function EmptyState({ message, tone = "neutral" }: EmptyStateProps) {
  return (
    <div className={`flex flex-col items-center gap-2 p-6 text-center ${TONE_CLASSES[tone]}`}>
      <p className="text-sm text-ink-secondary">{message}</p>
    </div>
  );
}
