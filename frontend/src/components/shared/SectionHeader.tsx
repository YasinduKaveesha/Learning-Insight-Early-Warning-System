import type { ReactNode } from "react";

export interface SectionHeaderProps {
  title: string;
  /** e.g. "Based on recent learning activity" — rendered under the title. */
  subtitle?: string;
  action?: ReactNode;
  /** UI-refinement pass: bumps the title from 16px/font-semibold to
   * 18px/font-bold — opt-in (false by default) so every other caller
   * keeps its original size/weight; used by StudentDetail's "Skill
   * progress" header. */
  boldTitle?: boolean;
}

export function SectionHeader({ title, subtitle, action, boldTitle = false }: SectionHeaderProps) {
  return (
    <div className="flex items-start justify-between gap-2 px-1 py-2">
      <div>
        <h2
          className={
            boldTitle
              ? "text-[19px] font-bold text-ink-primary"
              : "text-base font-semibold text-ink-primary"
          }
        >
          {title}
        </h2>
        {subtitle ? <p className="text-sm text-ink-secondary">{subtitle}</p> : null}
      </div>
      {action}
    </div>
  );
}
