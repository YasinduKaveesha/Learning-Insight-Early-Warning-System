import { gettingStartedProgress } from "../../lib/presentation";
import { NeutralNotice } from "../shared/NeutralNotice";

export interface GettingStartedNoticeProps {
  sessionsCompleted: number;
  sessionsRequired?: number;
  /** When given, personalises the notice for the Student Overview's
   * status-block replacement (plan §4.4): "<Name> is still building a
   * learning history — N of 3 sessions completed. ...". Omitted for the
   * compact cohort-card summary, which already shows the name beside it. */
  name?: string;
}

/**
 * "Getting Started", never "Insufficient Evidence" (docs/12 §3 — the
 * technical term sounds like a problem with the child). A first-class state,
 * never styled as a warning, never implying struggle — built on the shared
 * NeutralNotice card, no warning colours or icons.
 */
export function GettingStartedNotice({
  sessionsCompleted,
  sessionsRequired = 3,
  name,
}: GettingStartedNoticeProps) {
  return (
    <NeutralNotice title="Getting Started" tone={name ? "green" : "neutral"}>
      {name
        ? sessionsCompleted <= 0
          ? // A child who joined today has not started, which is different from
            // having started and not got far. "0 of 3 sessions completed" reads
            // as a stalled progress bar for someone with nothing to stall.
            `${name} has just joined and has not completed a session yet. After ${sessionsRequired} sessions the dashboard can start showing how they are getting on.`
          : `${name} is still building a learning history — ${sessionsCompleted} of ${sessionsRequired} sessions completed. More activity is needed before the system can identify a clear learning pattern.`
        : "This student is still building a learning history. More activity is needed before the system can identify a clear learning pattern."}
      {!name ? (
        <span className="mt-2 block text-sm text-ink-secondary">
          {gettingStartedProgress(sessionsCompleted, sessionsRequired)}
        </span>
      ) : null}
    </NeutralNotice>
  );
}
