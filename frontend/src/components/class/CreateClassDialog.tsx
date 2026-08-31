import { useId, useState } from "react";
import type { Grade } from "../../lib/presentation";
import { Dialog } from "../shared/Dialog";

export interface CreateClassDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (name: string, grade: Grade) => void;
  /** Rendered verbatim as an inline field error — e.g. a duplicate-name
   * message from the API. This component does not decide what counts as a
   * duplicate; it only displays the error it's given. */
  nameError?: string;
}

/** Grade select limited to Grade 2 / Grade 3 (D2). A duplicate name surfaces
 * as an inline field error via the `nameError` prop, never a crash. */
export function CreateClassDialog({
  isOpen,
  onClose,
  onSubmit,
  nameError,
}: CreateClassDialogProps) {
  const [name, setName] = useState("");
  const [grade, setGrade] = useState<Grade>("GRADE_3");
  const nameFieldId = useId();
  const gradeFieldId = useId();
  const errorId = useId();

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (name.trim().length === 0) return;
    onSubmit(name.trim(), grade);
  }

  return (
    <Dialog isOpen={isOpen} onClose={onClose} titleId="create-class-title" title="Create Class">
      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <div>
          <label htmlFor={nameFieldId} className="text-xs font-medium text-slate-700">
            Class name
          </label>
          <input
            id={nameFieldId}
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            aria-invalid={nameError ? true : undefined}
            aria-describedby={nameError ? errorId : undefined}
            className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-300 px-3 text-base"
          />
          {nameError ? (
            <p id={errorId} className="mt-1 text-xs text-red-600">
              {nameError}
            </p>
          ) : null}
        </div>

        <div>
          <label htmlFor={gradeFieldId} className="text-xs font-medium text-slate-700">
            Grade
          </label>
          <select
            id={gradeFieldId}
            value={grade}
            onChange={(e) => setGrade(e.target.value as Grade)}
            className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-300 px-3 text-base"
          >
            <option value="GRADE_2">Grade 2</option>
            <option value="GRADE_3">Grade 3</option>
          </select>
        </div>

        <button
          type="submit"
          className="min-h-[44px] rounded-lg bg-slate-900 px-3 text-sm font-medium text-white"
        >
          Create class
        </button>
      </form>
    </Dialog>
  );
}
