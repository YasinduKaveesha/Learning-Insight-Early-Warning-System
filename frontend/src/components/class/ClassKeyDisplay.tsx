import { useState } from "react";

export interface ClassKeyDisplayProps {
  classKey: string;
  /** "large" (ClassKeyDialog, shown once at creation — the primary element
   * on the screen) or "compact" (ClassInfoDialog, retrieved later among
   * other class details). Same key, same component, different emphasis. */
  size?: "large" | "compact";
  /** Show the "Copy key" button with its copied confirmation. Both dialogs
   * want this — the teacher may need to paste the key into a message
   * either at creation or when re-sharing it later. */
  showCopyButton?: boolean;
}

/**
 * THE ONE place the class key is rendered (Step 6: ClassKeyDialog and
 * ClassInfoDialog both use this rather than building a second key display).
 * Large, monospaced, letter-spaced — legible at arm's length when a teacher
 * reads it aloud to a room. aria-label spells it character by character so
 * a screen reader doesn't run it together as one word. The key is
 * PERMANENT (D1): this component has no regenerate control, and never will.
 */
export function ClassKeyDisplay({
  classKey,
  size = "large",
  showCopyButton = true,
}: ClassKeyDisplayProps) {
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

  const textSizeClass = size === "large" ? "py-4 text-3xl" : "py-3 text-2xl";

  return (
    <div>
      <p
        aria-label={spelledOut}
        className={`rounded-lg bg-surface2 text-center font-mono font-semibold tracking-[0.3em] text-ink-primary ${textSizeClass}`}
      >
        {classKey}
      </p>
      {showCopyButton ? (
        <button
          type="button"
          onClick={handleCopy}
          aria-live="polite"
          className="mt-3 min-h-[44px] w-full rounded-lg border border-border-strong text-sm font-medium text-ink-primary"
        >
          {copied ? "Copied" : "Copy key"}
        </button>
      ) : null}
    </div>
  );
}
