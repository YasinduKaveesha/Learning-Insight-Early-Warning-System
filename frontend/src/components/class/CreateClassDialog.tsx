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
          <label htmlFor={nameFieldId} className="text-sm font-medium text-ink-primary">
            Class name
          </label>
          <input
            id={nameFieldId}
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            aria-invalid={nameError ? true : undefined}
            aria-describedby={nameError ? errorId : undefined}
            className="mt-1 min-h-[44px] w-full rounded-lg border border-border-strong px-3 text-base"
          />
          {nameError ? (
            <p id={errorId} className="mt-1 text-sm text-danger-text">
              {nameError}
            </p>
          ) : null}
        </div>

        <div>
          <span id={gradeFieldId} className="text-sm font-medium text-ink-primary">
            Grade
          </span>
          {/* Two side-by-side buttons instead of a dropdown — both choices
              are visible at once rather than hidden behind a click. */}
          <div role="group" aria-labelledby={gradeFieldId} className="mt-1 flex gap-2">
            <button
              type="button"
              aria-pressed={grade === "GRADE_2"}
              onClick={() => setGrade("GRADE_2")}
              className={`min-h-[44px] flex-1 rounded-lg border px-3 text-base font-medium ${
                grade === "GRADE_2"
                  ? "border-watch-watching-fg bg-watch-watching-fg text-white"
                  : "border-border-strong bg-surface1 text-ink-primary"
              }`}
            >
              Grade 2
            </button>
            <button
              type="button"
              aria-pressed={grade === "GRADE_3"}
              onClick={() => setGrade("GRADE_3")}
              className={`min-h-[44px] flex-1 rounded-lg border px-3 text-base font-medium ${
                grade === "GRADE_3"
                  ? "border-watch-watching-fg bg-watch-watching-fg text-white"
                  : "border-border-strong bg-surface1 text-ink-primary"
              }`}
            >
              Grade 3
            </button>
          </div>
        </div>

        <button
          type="submit"
          className="min-h-[44px] rounded-full bg-watch-watching-fg px-3 text-sm font-bold text-white"
        >
          Create class
        </button>
      </form>
    </Dialog>
  );
}
