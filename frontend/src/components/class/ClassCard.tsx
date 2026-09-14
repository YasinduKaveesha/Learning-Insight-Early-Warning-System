import { GRADE_LABEL, type Grade } from "../../lib/presentation";

export interface ClassCardProps {
  name: string;
  grade: Grade;
  studentCount: number;
  toWatchCount: number;
  pendingRequestCount?: number;
  onClick?: () => void;
  /** UI-refinement pass: Home's cards opt into a taller, grade-coloured
   * look (same name + subtitle content as before); "default" (every other
   * caller — /classes, the gallery) keeps the original compact neutral
   * card, unchanged. */
  variant?: "default" | "colorful";
}

const GRADE_TONE_CLASSES: Record<Grade, string> = {
  // Reuses the same blue/green pair Home's stat tiles use, so the two
  // colour languages on the page agree with each other.
  GRADE_2: "border-watch-watching-border bg-watch-watching-bg text-watch-watching-fg",
  GRADE_3: "border-watch-noConcern-border bg-watch-noConcern-bg text-watch-noConcern-fg",
};

export function ClassCard({
  name,
  grade,
  studentCount,
  toWatchCount,
  pendingRequestCount,
  onClick,
  variant = "default",
}: ClassCardProps) {
  if (variant === "colorful") {
    return (
      <button
        type="button"
        onClick={onClick}
        className={`relative flex min-h-[88px] w-full flex-col justify-between gap-2 rounded-lg border p-3 text-left ${GRADE_TONE_CLASSES[grade]}`}
      >
        <p className="text-[15px] font-bold">{name}</p>
        <p className="self-end text-sm">
          <span className="text-[24px] font-semibold">{toWatchCount}</span> /{" "}
          <span className="text-[24px] font-semibold">{studentCount}</span>{" "}
          <span className="text-[12px]">watch</span>
        </p>
        {pendingRequestCount && pendingRequestCount > 0 ? (
          // UI-refinement pass: a plain red dot (not a numbered badge) —
          // "there's someone waiting to join," the count itself is inside
          // the classroom's own join-requests banner.
          <span
            aria-label={`${pendingRequestCount} join request${pendingRequestCount === 1 ? "" : "s"} pending`}
            className="absolute right-3 top-3 h-3 w-3 rounded-full bg-danger"
          />
        ) : null}
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      className="flex min-h-[44px] w-full items-center justify-between gap-2 rounded-lg border border-border bg-surface1 p-3 text-left"
    >
      <div>
        <p className="text-sm font-semibold text-ink-primary">{name}</p>
        <p className="text-sm text-ink-secondary">
          {GRADE_LABEL[grade]} · {studentCount} students · {toWatchCount} to watch
        </p>
      </div>
      {pendingRequestCount && pendingRequestCount > 0 ? (
        <span className="flex h-6 min-w-[24px] items-center justify-center rounded-full bg-primary px-1.5 text-sm font-bold text-foreground">
          {pendingRequestCount}
        </span>
      ) : null}
    </button>
  );
}
