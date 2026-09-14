import { lastActiveLabel } from "../../lib/format";
import {
  gettingStartedProgress,
  handledNote,
  toWatchStatus,
  trajectoryStateWord,
  type LearnerSnapshot,
  type WatchStatus,
} from "../../lib/presentation";
import { GettingStartedNotice } from "../status/GettingStartedNotice";

export interface StudentCardProps {
  snapshot: LearnerSnapshot;
  onClick?: () => void;
}

// UI-refinement pass: the card's own background/border now carries the
// watching/no-concern/getting-started distinction — reusing the SAME
// tokens Home's stat tiles already use for this exact three-way split
// (blue/green/amber), not new arbitrary colours. Never red for a watch
// status (docs/12 §7) — watching is blue, an invitation to look, not red.
// watch.gettingStarted (near-white) is NOT used here — it barely reads as
// a colour at all, which is why this card needed a visible one.
const STATUS_TONE_CLASSES: Record<WatchStatus["kind"], string> = {
  watching: "border-watch-watching-border bg-watch-watching-bg",
  no_concern: "border-watch-noConcern-border bg-watch-noConcern-bg",
  getting_started: "border-statAmber-border bg-statAmber-bg",
};

/** Name, practice trajectory word, last session (docs/11 §4). Getting
 * Started students render the notice instead of a trajectory word — there
 * is nothing to show a trend for yet.
 *
 * UI-refinement pass: the watch-status badge and the accuracy sparkline
 * chart are removed from this card entirely, and the trajectory reads as a
 * bare word ("stable"/"improving"/...) instead of the D13 chip (source
 * prefix + arrow) — see lib/presentation.ts's trajectoryStateWord. The
 * status is still never colour-alone (docs/11 §9): which SECTION a card
 * sits in ("Students to Watch" vs "All Students") already carries the
 * distinction in text, this is additive, not the only signal. */
export function StudentCard({ snapshot, onClick }: StudentCardProps) {
  const status = toWatchStatus(snapshot);
  const Wrapper = onClick ? "button" : "div";

  return (
    <Wrapper
      onClick={onClick}
      type={onClick ? "button" : undefined}
      className={`relative flex w-full min-h-[44px] flex-col gap-2 rounded-lg border p-3 text-left ${STATUS_TONE_CLASSES[status.kind]}`}
    >
      <span className="text-[17px] font-semibold text-ink-primary">{snapshot.displayName}</span>

      {/* Vertically centered on the whole card, right corner — independent
          of the name/last-active flow above and below it. */}
      {status.kind === "getting_started" ? (
        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[20px] text-ink-secondary">
          {gettingStartedProgress(status.sessionsCompleted, status.sessionsRequired)}
        </span>
      ) : (
        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[20px] text-ink-secondary">
          {trajectoryStateWord(snapshot.practiceTrajectory.state)}
        </span>
      )}

      <p className="text-sm text-ink-secondary">
        {lastActiveLabel(snapshot.lastActiveDate)}
      </p>
      {/* Decision B: says why a blue card is outside the watch section. */}
      {handledNote(snapshot) ? (
        <p className="text-sm font-semibold text-watch-watching-fg">{handledNote(snapshot)}</p>
      ) : null}
    </Wrapper>
  );
}

// Exported for screens that need the full Getting Started notice inline
// (e.g. the student overview) rather than the compact one-line summary above.
export { GettingStartedNotice };
