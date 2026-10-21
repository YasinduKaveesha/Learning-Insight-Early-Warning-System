export interface StatTileProps {
  label: string;
  value: number;
  /** Small secondary text, e.g. "of 83 students" — never a percentage. */
  caption?: string;
  infoText?: string;
  /** UI-refinement pass: an optional soft-tint colour + bold text + the
   * value pinned to the bottom-right corner. Undefined (the default) keeps
   * every existing caller's neutral surface1 tile exactly as it was —
   * this only changes tiles that opt in. */
  tone?: "blue" | "green" | "amber";
}

const TONE_CLASSES: Record<NonNullable<StatTileProps["tone"]>, string> = {
  blue: "border-toneCard-blue-border bg-toneCard-blue-bg text-white",
  green: "border-toneCard-green-border bg-toneCard-green-bg text-white",
  amber: "border-toneCard-amber-border bg-toneCard-amber-bg text-white",
};

export function StatTile({ label, value, caption, infoText, tone }: StatTileProps) {
  if (tone) {
    return (
      <div
        className={`flex min-h-[96px] flex-col justify-between gap-1 rounded-lg border p-3 ${TONE_CLASSES[tone]}`}
      >
        <div className="flex items-center gap-1 text-sm font-bold">
          <span>{label}</span>
          {infoText ? (
            <span
              role="img"
              aria-label={infoText}
              title={infoText}
              className="inline-flex h-4 w-4 items-center justify-center rounded-full border border-current text-[10px] leading-none"
            >
              i
            </span>
          ) : null}
        </div>
        <div className="self-end text-2xl font-bold">{value}</div>
        {caption ? <div className="self-end text-sm font-semibold">{caption}</div> : null}
      </div>
    );
  }

  return (
    <div className="flex min-h-[44px] flex-col gap-1 rounded-lg border border-border bg-surface1 p-3">
      <div className="flex items-center gap-1 text-sm font-medium text-ink-secondary">
        <span>{label}</span>
        {infoText ? (
          <span
            role="img"
            aria-label={infoText}
            title={infoText}
            className="inline-flex h-4 w-4 items-center justify-center rounded-full border border-border-strong text-[10px] leading-none text-ink-secondary"
          >
            i
          </span>
        ) : null}
      </div>
      <div className="text-2xl font-semibold text-ink-primary">{value}</div>
      {caption ? <div className="text-sm text-ink-secondary">{caption}</div> : null}
    </div>
  );
}
