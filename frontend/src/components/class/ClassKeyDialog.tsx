import { ClassKeyDisplay } from "./ClassKeyDisplay";
import { Dialog } from "../shared/Dialog";

export interface ClassKeyDialogProps {
  isOpen: boolean;
  onClose: () => void;
  className: string;
  classKey: string;
  /** Navigates to the new classroom — shown only right after creation, when
   * this dialog is the "Created → Class Key → Classroom" step of the flow
   * (plan §4.7). Omitted when this dialog is reused elsewhere. */
  onGoToClass?: () => void;
}

/**
 * THE PRIMARY ELEMENT on this screen — shown immediately on class creation.
 * Reuses ClassKeyDisplay (large) rather than a second key rendering; see
 * that component's doc comment for the accessibility and D1 permanence
 * contract.
 */
export function ClassKeyDialog({
  isOpen,
  onClose,
  className,
  classKey,
  onGoToClass,
}: ClassKeyDialogProps) {
  return (
    <Dialog isOpen={isOpen} onClose={onClose} titleId="class-key-title" title="Class Key">
      <p className="text-sm text-ink-secondary">{className}</p>
      <div className="my-4">
        <ClassKeyDisplay classKey={classKey} size="large" />
      </div>
      <p className="text-xs text-ink-secondary">
        Give this key to your students so they can join the class.
      </p>
      {onGoToClass ? (
        <button
          type="button"
          onClick={onGoToClass}
          className="mt-4 min-h-[44px] w-full rounded-lg bg-primary text-sm font-bold text-foreground"
        >
          Go to class
        </button>
      ) : null}
    </Dialog>
  );
}
