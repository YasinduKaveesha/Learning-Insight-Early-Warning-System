export interface ClassCardProps {
  name: string;
  grade: "GRADE_2" | "GRADE_3";
  studentCount: number;
  toWatchCount: number;
  pendingRequestCount?: number;
  onClick?: () => void;
}

const GRADE_LABEL: Record<ClassCardProps["grade"], string> = {
  GRADE_2: "Grade 2",
  GRADE_3: "Grade 3",
};

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
      className="flex min-h-[44px] w-full items-center justify-between gap-2 rounded-lg border border-slate-200 bg-white p-3 text-left"
    >
      <div>
        <p className="text-sm font-semibold text-slate-900">{name}</p>
        <p className="text-xs text-slate-500">
          {GRADE_LABEL[grade]} · {studentCount} students · {toWatchCount} to watch
        </p>
      </div>
      {pendingRequestCount && pendingRequestCount > 0 ? (
        <span className="flex h-6 min-w-[24px] items-center justify-center rounded-full bg-slate-900 px-1.5 text-xs font-semibold text-white">
          {pendingRequestCount}
        </span>
      ) : null}
    </button>
  );
}
