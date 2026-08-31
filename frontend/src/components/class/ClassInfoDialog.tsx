import { Dialog } from "../shared/Dialog";

export interface ClassInfoDialogProps {
  isOpen: boolean;
  onClose: () => void;
  className: string;
  grade: "GRADE_2" | "GRADE_3";
  classKey: string;
}

const GRADE_LABEL: Record<ClassInfoDialogProps["grade"], string> = {
  GRADE_2: "Grade 2",
  GRADE_3: "Grade 3",
};

/** The permanent class key (D1), retrievable at any time from the classroom
 * ⓘ — the same key shown at creation, never regenerated. */
export function ClassInfoDialog({
  isOpen,
  onClose,
  className,
  grade,
  classKey,
}: ClassInfoDialogProps) {
  const spelledOut = classKey.split("").join(" ");
  return (
    <Dialog isOpen={isOpen} onClose={onClose} titleId="class-info-title" title="Class Info">
      <p className="text-sm text-slate-700">{className}</p>
      <p className="text-xs text-slate-500">{GRADE_LABEL[grade]}</p>
      <p className="mt-2 text-xs font-medium text-slate-700">Class key</p>
      <p
        aria-label={spelledOut}
        className="mt-1 rounded-lg bg-slate-100 py-3 text-center font-mono text-2xl font-semibold tracking-[0.3em] text-slate-900"
      >
        {classKey}
      </p>
    </Dialog>
  );
}
