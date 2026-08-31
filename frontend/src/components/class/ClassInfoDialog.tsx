import { GRADE_LABEL, type Grade } from "../../lib/presentation";
import { ClassKeyDisplay } from "./ClassKeyDisplay";
import { Dialog } from "../shared/Dialog";

export interface ClassInfoDialogProps {
  isOpen: boolean;
  onClose: () => void;
  className: string;
  grade: Grade;
  classKey: string;
  studentCount: number;
}

/** The permanent class key (D1), retrievable at any time from the classroom
 * ⓘ — the SAME key shown at creation, never regenerated. Reuses
 * ClassKeyDisplay rather than building a second key rendering (Step 6). */
export function ClassInfoDialog({
  isOpen,
  onClose,
  className,
  grade,
  classKey,
  studentCount,
}: ClassInfoDialogProps) {
  return (
    <Dialog isOpen={isOpen} onClose={onClose} titleId="class-info-title" title="Class Info">
      <p className="text-sm text-ink-primary">{className}</p>
      <p className="text-sm text-ink-secondary">
        {GRADE_LABEL[grade]} · {studentCount} student{studentCount === 1 ? "" : "s"}
      </p>
      <p className="mt-3 text-sm font-medium text-ink-primary">Class key</p>
      <div className="mt-1">
        <ClassKeyDisplay classKey={classKey} size="compact" />
      </div>
    </Dialog>
  );
}
