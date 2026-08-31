export interface StatTileProps {
  label: string;
  value: number;
  /** Small secondary text, e.g. "of 83 students" — never a percentage. */
  caption?: string;
  infoText?: string;
}

export function StatTile({ label, value, caption, infoText }: StatTileProps) {
  return (
    <div className="flex min-h-[44px] flex-col gap-1 rounded-lg border border-slate-200 bg-white p-3">
      <div className="flex items-center gap-1 text-xs font-medium text-slate-500">
        <span>{label}</span>
        {infoText ? (
          <span
            role="img"
            aria-label={infoText}
            title={infoText}
            className="inline-flex h-4 w-4 items-center justify-center rounded-full border border-slate-300 text-[10px] leading-none text-slate-500"
          >
            i
          </span>
        ) : null}
      </div>
      <div className="text-2xl font-semibold text-slate-900">{value}</div>
      {caption ? <div className="text-xs text-slate-500">{caption}</div> : null}
    </div>
  );
}
