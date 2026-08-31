import { GRADE_LABEL, type Grade } from "../../lib/presentation";

export interface ClassCardProps {
  name: string;
  grade: Grade;
  studentCount: number;
  toWatchCount: number;
  pendingRequestCount?: number;
  onClick?: () => void;
}

export function ClassCard({
  name,
  grade,
  studentCount,
  toWatchCount,
  pendingRequestCount,
  onClick,
}: ClassCardProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex min-h-[44px] w-full items-center justify-between gap-2 rounded-lg border border-border bg-surface1 p-3 text-left"
    >
      <div>
        <p className="text-sm font-semibold text-ink-primary">{name}</p>
        <p className="text-xs text-ink-secondary">
          {GRADE_LABEL[grade]} · {studentCount} students · {toWatchCount} to watch
        </p>
      </div>
      {pendingRequestCount && pendingRequestCount > 0 ? (
        <span className="flex h-6 min-w-[24px] items-center justify-center rounded-full bg-primary px-1.5 text-xs font-bold text-foreground">
          {pendingRequestCount}
        </span>
      ) : null}
    </button>
  );
}
