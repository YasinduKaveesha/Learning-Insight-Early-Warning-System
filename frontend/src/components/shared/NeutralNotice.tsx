import type { ReactNode } from "react";

export interface NeutralNoticeProps {
  title: string;
  children: ReactNode;
  /** UI-refinement pass: "green" matches the watch.noConcern card style
   * used by Student Overview's status block (same rounded-lg/p-4/colour
   * shape) — opt-in so Reports' "not enough history yet" notice keeps its
   * original neutral-grey look. */
  tone?: "neutral" | "green";
}

const TONE_CLASSES: Record<NonNullable<NeutralNoticeProps["tone"]>, string> = {
  neutral: "rounded-md border border-border bg-surface2",
  green: "rounded-lg border border-watch-noConcern-border bg-watch-noConcern-bg",
};

/**
 * The shared "the system is declining to guess" card — neutral tone, never
 * styled as a warning or an error (docs/12 §7). GettingStartedNotice uses
 * this for a student below the warm-up floor; Reports' "students to watch
 * over time" section (Step 8 fix) uses it for "not enough history yet".
 * Both are the same kind of honest absence, so they share one visual
 * treatment rather than each inventing its own.
 */
export function NeutralNotice({ title, children, tone = "neutral" }: NeutralNoticeProps) {
  return (
    <div className={`p-4 ${TONE_CLASSES[tone]}`}>
      <p className="text-sm font-bold text-ink-primary">{title}</p>
      <p className="mt-1 text-sm text-ink-secondary">{children}</p>
    </div>
  );
}
