import { useEffect, useRef, type ReactNode } from "react";

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

export interface DialogProps {
  isOpen: boolean;
  onClose: () => void;
  titleId: string;
  title: string;
  children: ReactNode;
  /** "sheet" (default): a bottom sheet on phones, centred from 640px up.
   * "center": always centred both ways over a blurred page, with no close
   * button -- for a confirmation whose own buttons are the only way out
   * (Escape still closes it). */
  placement?: "sheet" | "center";
}

/**
 * Base modal: role="dialog", aria-labelledby, traps focus, closes on Escape,
 * restores focus to whatever triggered it (plan §9). Every other dialog in
 * this app (ClassKeyDialog, CreateClassDialog, ClassInfoDialog) is built on
 * this one so the accessibility contract lives in exactly one place.
 */
export function Dialog({
  isOpen,
  onClose,
  titleId,
  title,
  children,
  placement = "sheet",
}: DialogProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    previouslyFocused.current = document.activeElement as HTMLElement | null;

    const panel = panelRef.current;
    const focusables = panel?.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
    (focusables?.[0] ?? panel)?.focus();

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key !== "Tab" || !panel) return;
      const items = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
      if (items.length === 0) return;
      const first = items[0]!;
      const last = items[items.length - 1]!;
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      previouslyFocused.current?.focus();
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  if (placement === "center") {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/30 px-4 backdrop-blur-sm">
        <div
          ref={panelRef}
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          tabIndex={-1}
          className="w-full max-w-sm rounded-2xl bg-surface1 p-5 shadow-elevated"
        >
          <h2 id={titleId} className="mb-3 text-xl font-bold text-ink-primary">
            {title}
          </h2>
          {children}
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-foreground/40 sm:items-center">
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-t-2xl bg-surface1 p-5 shadow-elevated sm:rounded-2xl"
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 id={titleId} className="text-lg font-semibold text-ink-primary">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="flex h-11 w-11 items-center justify-center rounded-full text-ink-secondary hover:bg-surface2"
          >
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
