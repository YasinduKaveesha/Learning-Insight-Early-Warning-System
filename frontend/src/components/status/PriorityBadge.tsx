import { SNAPSHOT_FRAMING } from "../../lib/presentation";

export interface PriorityBadgeProps {
  /** Position within the list that produced it — 1-based. Never render this
   * value outside the list it came from (plan §1: rank is a snapshot
   * property, not a standing the child holds). */
  priority: number;
}

export function PriorityBadge({ priority }: PriorityBadgeProps) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-sm font-semibold text-slate-900">Priority {priority}</span>
      <span className="text-xs text-slate-500">{SNAPSHOT_FRAMING}</span>
    </div>
  );
}
