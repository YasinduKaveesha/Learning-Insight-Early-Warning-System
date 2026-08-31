// The only place ML becomes teacher language (plan §5, §6).
// No RiskLevel type exists here on purpose.

import type {
  LearnerSnapshot,
  RecommendationKind,
  SessionEntry,
  SkillProgress,
  Trajectory,
} from "../api/types";

/** Exhaustiveness guard — a switch that forgets a case fails to compile. */
export function assertNever(x: never): never {
  throw new Error(`Unhandled case: ${JSON.stringify(x)}`);
}

// --- Watch status -----------------------------------------------------

export type WatchStatus =
  | { kind: "watching"; label: "Worth watching right now"; priority: number | null }
  | { kind: "no_concern"; label: "No current concern identified" }
  | {
      kind: "getting_started";
      label: "Getting Started";
      sessionsCompleted: number;
      sessionsRequired: 3;
    };

export function toWatchStatus(s: LearnerSnapshot): WatchStatus {
  if (s.evidenceStatus !== "sufficient_evidence") {
    return {
      kind: "getting_started",
      label: "Getting Started",
      sessionsCompleted: s.sessionsCompleted,
      sessionsRequired: 3,
    };
  }
  if (s.watchFlag) {
    return {
      kind: "watching",
      label: "Worth watching right now",
      priority: s.rankWithinSnapshot,
    };
  }
  return { kind: "no_concern", label: "No current concern identified" };
}

/** Exhaustive icon/text pairing so colour can never be the only cue (plan §9). */
export function watchStatusIcon(status: WatchStatus): string {
  switch (status.kind) {
    case "watching":
      return "◐";
    case "no_concern":
      return "○";
    case "getting_started":
      return "◔";
    default:
      return assertNever(status);
  }
}

// --- Trajectory (D12, D13) ---------------------------------------------

const TRAJECTORY_SOURCE_LABEL: Record<Trajectory["source"], string> = {
  practice_accuracy: "Practice accuracy",
  game_engagement: "Game engagement",
};

const TRAJECTORY_STATE_LABEL: Record<Trajectory["state"], string> = {
  improving: "improving ↑",
  stable: "stable →",
  needs_attention: "needs attention ↓",
  unknown: "not enough data",
};

/**
 * Every trajectory is rendered with its source prefix (D13) — there is no code
 * path that can produce a bare, unlabelled trajectory string.
 */
export function trajectoryLabel(t: Trajectory): string {
  return `${TRAJECTORY_SOURCE_LABEL[t.source]}: ${TRAJECTORY_STATE_LABEL[t.state]}`;
}

// --- Skill progress ------------------------------------------------------

const SKILL_DIRECTION_LABEL: Record<SkillProgress["direction"], string> = {
  improving: "improving",
  not_moving: "not moving",
  unknown: "not enough data", // never "flat"
};

export function skillDirectionLabel(direction: SkillProgress["direction"]): string {
  return SKILL_DIRECTION_LABEL[direction];
}

/**
 * `relativeLevel` is a bar position ONLY. Returns a 0-100 number for a CSS
 * width/position — never a string, so it cannot be rendered as a number or
 * percentage to the teacher. A null or out-of-range value collapses to 0
 * (an empty bar), which reads as "not enough data" alongside the direction
 * label rather than as a real position.
 */
export function skillBarPosition(relativeLevel: number | null): number {
  if (relativeLevel === null || Number.isNaN(relativeLevel)) return 0;
  return Math.min(100, Math.max(0, relativeLevel * 100));
}

// --- Session activity gaps -------------------------------------------------

/**
 * Distinguishes "no activity recorded" (component absent) from "activity data
 * incomplete" (present but telemetry was faulty) — these must never collapse
 * into one message (plan §4.5 rule 2 & 3). Returns null when the component's
 * real data should be rendered instead of a gap message.
 */
export function sessionComponentGapLabel(component: {
  present: boolean;
  dataComplete?: boolean;
}): string | null {
  if (!component.present) return "No activity recorded";
  if (component.dataComplete === false) return "Activity data incomplete for this session";
  return null;
}

export function gamesGapLabel(games: SessionEntry["games"]): string | null {
  return sessionComponentGapLabel(games);
}

// --- Recommendations (D7) -------------------------------------------------

const RECOMMENDATION_LABEL: Record<RecommendationKind, string> = {
  practice: "Practice",
  review: "Review",
  try_again: "Try Again",
  monitor_progress: "Monitor Progress",
};

const RECOMMENDATION_FALLBACK = "Suggestion";

/** An unrecognised kind renders a readable fallback — it must never throw. */
export function recommendationLabel(kind: string): string {
  return (RECOMMENDATION_LABEL as Record<string, string>)[kind] ?? RECOMMENDATION_FALLBACK;
}

// --- Snapshot framing (plan §1, §6) ---------------------------------------

export const SNAPSHOT_FRAMING = "Based on recent learning activity";

// --- Explanation filters (plan §7, defence in depth) ------------------------

// 1. The time / observation index is never a reason.
const TIME_INDEX_PATTERN =
  /observation (history|index|window)|longer (observation|history)|session index|time index|calendar/i;

// 2. No protective or reassuring sentence on a flagged student.
const PROTECTIVE_PATTERN =
  /healthy pace|progressing (well|nicely)|doing (well|great|fine)|on track|no concern|good progress|nothing to worry|performing well/i;

/**
 * Applies both filters from plan §7. Returns null when the explanation must
 * be suppressed rather than shown to a teacher.
 */
export function filterExplanation(
  explanation: string | null,
  watchFlag: boolean,
): string | null {
  if (explanation === null) return null;
  if (TIME_INDEX_PATTERN.test(explanation)) return null;
  if (watchFlag && PROTECTIVE_PATTERN.test(explanation)) return null;
  return explanation;
}
