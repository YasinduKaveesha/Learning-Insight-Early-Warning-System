import { SNAPSHOT_FRAMING } from "../../lib/presentation";

export interface PriorityBadgeProps {
  /** Position within the list that produced it — 1-based. Never render this
   * value outside the list it came from (plan §1: rank is a snapshot
   * property, not a standing the child holds). */
  priority: number;
  /** Optional trailing context, e.g. "in Grade 3 Blue" (plan §4.4's "Priority
   * 1 in Grade 3 Blue" on the Student Overview status block). Omitted in a
   * list already scoped to one class, where it would be redundant. */
  context?: string;
}

export function PriorityBadge({ priority, context }: PriorityBadgeProps) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-sm font-semibold text-slate-900">
        Priority {priority}
        {context ? ` ${context}` : ""}
      </span>
      <span className="text-xs text-slate-500">{SNAPSHOT_FRAMING}</span>
    </div>
  );
}
