import { assertNever, type WatchStatus, watchStatusIcon } from "../../lib/presentation";

const STATE_CLASS: Record<WatchStatus["kind"], string> = {
  watching: "bg-watch-watching-bg text-watch-watching-fg border-watch-watching-border",
  no_concern: "bg-watch-noConcern-bg text-watch-noConcern-fg border-watch-noConcern-border",
  getting_started:
    "bg-watch-gettingStarted-bg text-watch-gettingStarted-fg border-watch-gettingStarted-border",
};

export interface WatchStatusBadgeProps {
  status: WatchStatus;
}

/**
 * The single most likely place for a null-coalescing default to silently
 * turn "we don't know" into "no concern" (docs/15 §7). The discriminated
 * union plus assertNever means a missing case is a compile error, not a
 * runtime default — there is no `default: "no_concern"` branch possible.
 * Icon AND text always; colour is only ever a secondary cue (plan §9).
 */
export function WatchStatusBadge({ status }: WatchStatusBadgeProps) {
  const className = pickClass(status);
  return (
    <span
      className={`inline-flex min-h-[28px] items-center gap-1.5 rounded-full border px-2.5 py-1 text-sm font-medium ${className}`}
    >
      <span aria-hidden="true">{watchStatusIcon(status)}</span>
      <span>{status.label}</span>
    </span>
  );
}

function pickClass(status: WatchStatus): string {
  switch (status.kind) {
    case "watching":
      return STATE_CLASS.watching;
    case "no_concern":
      return STATE_CLASS.no_concern;
    case "getting_started":
      return STATE_CLASS.getting_started;
    default:
      return assertNever(status);
  }
}
