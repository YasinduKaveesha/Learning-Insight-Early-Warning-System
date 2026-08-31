import type { ReactNode } from "react";

export interface SectionHeaderProps {
  title: string;
  /** e.g. "Based on recent learning activity" — rendered under the title. */
  subtitle?: string;
  action?: ReactNode;
}

export function SectionHeader({ title, subtitle, action }: SectionHeaderProps) {
  return (
    <div className="flex items-start justify-between gap-2 px-1 py-2">
      <div>
        <h2 className="text-base font-semibold text-ink-primary">{title}</h2>
        {subtitle ? <p className="text-xs text-ink-secondary">{subtitle}</p> : null}
      </div>
      {action}
    </div>
  );
}
