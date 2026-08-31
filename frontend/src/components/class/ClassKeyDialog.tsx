import { useState } from "react";
import { Dialog } from "../shared/Dialog";

export interface ClassKeyDialogProps {
  isOpen: boolean;
  onClose: () => void;
  className: string;
  classKey: string;
}

/** Large, monospaced, letter-spaced — legible at arm's length when a teacher
 * reads it aloud to a room. aria-label spells it character by character so a
 * screen reader doesn't run it together as one word. */
export function ClassKeyDialog({ isOpen, onClose, className, classKey }: ClassKeyDialogProps) {
  const [copied, setCopied] = useState(false);
  const spelledOut = classKey.split("").join(" ");

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(classKey);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access can be denied by the browser; the key is still
      // visible and selectable, so this is not an error state to surface.
    }
  }

  return (
    <Dialog isOpen={isOpen} onClose={onClose} titleId="class-key-title" title="Class Key">
      <p className="text-sm text-slate-600">{className}</p>
      <p
        aria-label={spelledOut}
        className="my-4 rounded-lg bg-slate-100 py-4 text-center font-mono text-3xl font-semibold tracking-[0.35em] text-slate-900"
      >
        {classKey}
      </p>
      <button
        type="button"
        onClick={handleCopy}
        className="min-h-[44px] w-full rounded-lg border border-slate-300 text-sm font-medium text-slate-800"
      >
        {copied ? "Copied" : "Copy key"}
      </button>
      <p className="mt-3 text-xs text-slate-500">
        Give this key to your students so they can join the class.
      </p>
    </Dialog>
  );
}
