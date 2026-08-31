import { formatDate } from "../../lib/format";
import { sessionComponentGapLabel, type SessionEntry } from "../../lib/presentation";

export interface SessionCardProps {
  session: SessionEntry;
}

/**
 * B and C in SEPARATE blocks, never merged into one accuracy or timing value
 * (D2 / 3-F9). Session number displayed exactly as given (D9) — never
 * renumbered client-side. A technical fault (dataComplete: false) is never
 * rendered as disengagement — it gets its own distinct message from an
 * absent component (plan §4.5).
 */
export function SessionCard({ session }: SessionCardProps) {
  const gamesGap = sessionComponentGapLabel(session.games);

  return (
    <div className="rounded-lg border border-border bg-surface1 p-3">
      <div className="mb-2 flex items-baseline justify-between">
        <span className="text-sm font-semibold text-ink-primary">
          Session {session.sessionNumber}
        </span>
        <span className="text-xs text-ink-secondary">{formatDate(session.date)}</span>
      </div>

      <div className="border-t border-border pt-2">
        <p className="text-xs font-medium text-ink-secondary">Practice (B)</p>
        {session.practice.present ? (
          <p className="text-sm text-ink-primary">
            {session.practice.accuracy !== null
              ? `Accuracy ${Math.round(session.practice.accuracy * 100)}%`
              : "Accuracy not available"}
            {session.practice.pace ? ` · ${paceLabel(session.practice.pace)}` : ""}
            {session.practice.hintsUsed !== null
              ? ` · ${session.practice.hintsUsed} hint${session.practice.hintsUsed === 1 ? "" : "s"} used`
              : ""}
          </p>
        ) : (
          <p className="text-sm text-ink-secondary">No activity recorded</p>
        )}
      </div>

      <div className="mt-2 border-t border-border pt-2">
        <p className="text-xs font-medium text-ink-secondary">Games (C)</p>
        {gamesGap ? (
          <p className="text-sm text-ink-secondary">{gamesGap}</p>
        ) : (
          <p className="text-sm text-ink-primary">
            {session.games.engagementDriver
              ? `Engagement: ${session.games.engagementDriver}`
              : "Engagement data not available"}
            {session.games.frustrationDriver ? ` · Frustration: ${session.games.frustrationDriver}` : ""}
          </p>
        )}
      </div>
    </div>
  );
}

function paceLabel(pace: "faster" | "typical" | "slower"): string {
  switch (pace) {
    case "faster":
      return "Faster pace";
    case "typical":
      return "Typical pace";
    case "slower":
      return "Slower pace";
  }
}
