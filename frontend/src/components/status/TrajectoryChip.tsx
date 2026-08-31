import { type PracticeTrajectory, practiceTrajectoryLabel } from "../../lib/presentation";

export interface TrajectoryChipProps {
  /** Practice accuracy only (D17) — the prop type itself makes an engagement
   * trajectory chip impossible to construct. */
  trajectory: PracticeTrajectory;
}

/** Cannot render without its source prefix (D13) — practiceTrajectoryLabel
 * always returns "Practice accuracy: <state>", never a bare state. */
export function TrajectoryChip({ trajectory }: TrajectoryChipProps) {
  return (
    <span className="inline-flex items-center rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-700">
      {practiceTrajectoryLabel(trajectory)}
    </span>
  );
}
