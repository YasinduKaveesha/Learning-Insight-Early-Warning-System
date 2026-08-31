import { formatRelativeDate } from "../../lib/format";
import { type LearnerSnapshot, toWatchStatus } from "../../lib/presentation";
import { GettingStartedNotice } from "../status/GettingStartedNotice";
import { TrajectoryChip } from "../status/TrajectoryChip";
import { WatchStatusBadge } from "../status/WatchStatusBadge";
import { MiniSparkline } from "./MiniSparkline";

export interface StudentCardProps {
  snapshot: LearnerSnapshot;
  onClick?: () => void;
}

/** Name, watch badge, practice trajectory, accuracy sparkline, last session
 * (docs/11 §4). Getting Started students render the notice instead of a
 * trajectory chip — there is nothing to show a trend for yet. */
export function StudentCard({ snapshot, onClick }: StudentCardProps) {
  const status = toWatchStatus(snapshot);
  const Wrapper = onClick ? "button" : "div";

  return (
    <Wrapper
      onClick={onClick}
      type={onClick ? "button" : undefined}
      className="flex w-full min-h-[44px] flex-col gap-2 rounded-lg border border-slate-200 bg-white p-3 text-left"
    >
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm font-semibold text-slate-900">{snapshot.displayName}</span>
        <WatchStatusBadge status={status} />
      </div>

      {status.kind === "getting_started" ? (
        <p className="text-xs text-slate-500">
          {status.sessionsCompleted} of {status.sessionsRequired} sessions
        </p>
      ) : (
        <div className="flex items-center justify-between gap-2">
          <TrajectoryChip trajectory={snapshot.practiceTrajectory} />
          <MiniSparkline values={snapshot.accuracySparkline} />
        </div>
      )}

      <p className="text-xs text-slate-400">
        Last active {formatRelativeDate(snapshot.lastActiveDate)}
      </p>
    </Wrapper>
  );
}

// Exported for screens that need the full Getting Started notice inline
// (e.g. the student overview) rather than the compact one-line summary above.
export { GettingStartedNotice };
