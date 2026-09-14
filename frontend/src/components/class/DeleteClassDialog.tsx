import { useEffect, useId, useRef, useState } from "react";
import { Dialog } from "../shared/Dialog";

export interface DeleteClassDialogProps {
  isOpen: boolean;
  className: string;
  /** Resolves when the class is deleted; rejects to show an error in place. */
  onConfirm: (confirmationName: string) => Promise<void>;
  onCancel: () => void;
}

type Step = "ask" | "type-name";

/**
 * Deleting a class takes two deliberate steps (2026-09-14):
 *
 *   1. "Are you sure?" -- No or Yes.
 *   2. Type the class name, shown right there, and press Delete again.
 *
 * Both steps sit in ONE grid cell, the hidden one kept in layout with
 * `invisible`, so the panel is exactly the same size on both -- it does not
 * jump when the teacher moves from one to the other.
 *
 * The second Delete stays disabled until the typed name matches exactly (ends
 * trimmed, case kept). The student app checks the same thing on the server, so
 * this is a convenience, not the safeguard.
 */
export function DeleteClassDialog({ isOpen, className, onConfirm, onCancel }: DeleteClassDialogProps) {
  const [step, setStep] = useState<Step>("ask");
  const [typed, setTyped] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputId = useId();
  const titleId = useId();
  const inputRef = useRef<HTMLInputElement>(null);

  // Every opening starts again from step 1 with an empty field.
  useEffect(() => {
    if (isOpen) {
      setStep("ask");
      setTyped("");
      setError(null);
      setIsDeleting(false);
    }
  }, [isOpen]);

  // Moving to step 2 puts the cursor straight in the name field.
  useEffect(() => {
    if (step === "type-name") inputRef.current?.focus();
  }, [step]);

  const matches = typed.trim() === className.trim() && className.trim() !== "";

  async function handleDelete() {
    if (!matches || isDeleting) return;
    setIsDeleting(true);
    setError(null);
    try {
      await onConfirm(typed);
    } catch {
      setError("Couldn't delete this class. Try again.");
      setIsDeleting(false);
    }
  }

  const deleteButton =
    "min-h-[48px] flex-1 rounded-full bg-danger px-3 text-base font-bold text-foreground disabled:opacity-40";
  const cancelButton =
    "min-h-[48px] flex-1 rounded-full border-2 border-border-strong bg-surface1 px-3 text-base font-semibold text-ink-primary";

  return (
    <Dialog
      isOpen={isOpen}
      onClose={onCancel}
      titleId={titleId}
      // One title for both steps, so the panel's height does not change with it.
      title={`Delete “${className}”?`}
      placement="center"
    >
      <div className="grid">
        <div
          className={`col-start-1 row-start-1 flex flex-col gap-4 ${step === "ask" ? "" : "invisible"}`}
          aria-hidden={step !== "ask"}
        >
          <p className="text-base text-ink-secondary">
            Are you sure you want to delete this class?
          </p>
          <div className="mt-auto flex gap-3">
            <button
              type="button"
              onClick={onCancel}
              tabIndex={step === "ask" ? 0 : -1}
              className={cancelButton}
            >
              No
            </button>
            <button
              type="button"
              onClick={() => setStep("type-name")}
              tabIndex={step === "ask" ? 0 : -1}
              className={deleteButton}
            >
              Yes
            </button>
          </div>
        </div>

        <form
          className={`col-start-1 row-start-1 flex flex-col gap-3 ${step === "type-name" ? "" : "invisible"}`}
          aria-hidden={step !== "type-name"}
          onSubmit={(e) => {
            e.preventDefault();
            void handleDelete();
          }}
        >
          {/* A failure replaces this line rather than adding one, so the
              panel never grows taller than step 1. */}
          {error ? (
            <p role="alert" className="text-base text-danger-text">
              {error}
            </p>
          ) : (
            <p className="text-base text-ink-secondary">
              Type <span className="font-bold text-ink-primary">“{className}”</span> to confirm
            </p>
          )}
          <input
            ref={inputRef}
            id={inputId}
            aria-label={`Type ${className} to confirm`}
            type="text"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            autoComplete="off"
            spellCheck={false}
            tabIndex={step === "type-name" ? 0 : -1}
            className="min-h-[44px] w-full rounded-full border border-border-strong px-4 text-base"
          />
          <div className="mt-auto flex gap-3">
            <button
              type="button"
              onClick={onCancel}
              tabIndex={step === "type-name" ? 0 : -1}
              className={cancelButton}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!matches || isDeleting}
              tabIndex={step === "type-name" ? 0 : -1}
              className={deleteButton}
            >
              {isDeleting ? "Deleting…" : "Delete"}
            </button>
          </div>
        </form>
      </div>
    </Dialog>
  );
}
