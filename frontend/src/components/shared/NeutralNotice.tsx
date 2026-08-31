import type { ReactNode } from "react";

export interface NeutralNoticeProps {
  title: string;
  children: ReactNode;
}

/**
 * The shared "the system is declining to guess" card — neutral tone, never
 * styled as a warning or an error (docs/12 §7). GettingStartedNotice uses
 * this for a student below the warm-up floor; Reports' "students to watch
 * over time" section (Step 8 fix) uses it for "not enough history yet".
 * Both are the same kind of honest absence, so they share one visual
 * treatment rather than each inventing its own.
 */
export function NeutralNotice({ title, children }: NeutralNoticeProps) {
  return (
    <div className="rounded-md border border-border bg-surface2 p-4">
      <p className="text-sm font-bold text-ink-primary">{title}</p>
      <p className="mt-1 text-sm text-ink-secondary">{children}</p>
    </div>
  );
}
