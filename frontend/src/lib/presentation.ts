// The only place ML becomes teacher language (plan §5, §6).
// No RiskLevel type exists here on purpose.

import type {
  EvidenceStatus,
  LearnerSnapshot,
  RecommendationKind,
  SessionEntry,
  SkillProgress,
  Trajectory,
  TrajectoryState,
} from "../api/types";

// Re-exported so components import display shapes from THIS file only, never
// from api/types.ts directly (plan §5) — the single boundary a test can
// enforce by scanning import specifiers. These shapes are already free of
// every banned ML field (Step 3 tests assert it), so re-exporting them here
// is the translation layer's job, not a bypass of it.
export type { EvidenceStatus, LearnerSnapshot, SessionEntry, SkillProgress, TrajectoryState };

/** Exhaustiveness guard — a switch that forgets a case fails to compile. */
export function assertNever(x: never): never {
  throw new Error(`Unhandled case: ${JSON.stringify(x)}`);
}

// --- Framing (docs/12 §1, docs/15 §7) --------------------------------------

/** Exact required wording — no paraphrase, ever. Renders in the header of
 * every analytics surface via FramingLine. */
export const FRAMING_LINE = "The system flags learners for teacher review.";

// --- Trajectory (D13, D17) --------------------------------------------------

/**
 * D17: only the practice trajectory ships as a rendered state chip. This
 * type exists so TrajectoryChip's prop can be restricted to
 * "practice_accuracy" at compile time — there is no display-layer shape for
 * an engagement trajectory STATE for a component to accidentally accept.
 */
export type PracticeTrajectory = { source: "practice_accuracy"; state: TrajectoryState };

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

/** TrajectoryChip's only entry point — the parameter type itself forbids an
 * engagement trajectory from ever reaching a rendered chip (D17). */
export function practiceTrajectoryLabel(t: PracticeTrajectory): string {
  return trajectoryLabel(t);
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
 * `relativeLevel` is a bar position ONLY, never a labelled number or
 * percentage (plan §4.4). Returns a 0-100 number for a CSS width, or `null`
 * when there is no bar to draw at all.
 *
 * `null` must NOT collapse to 0: an empty bar reads as "lowest level", which
 * is a real (if minimal) position — exactly the failure the nullable design
 * exists to prevent (plan §4.4, §8: "no slope null becomes 0"). A null
 * `relativeLevel` means "we don't know", so the caller renders no bar.
 *
 * SCALE IS UNDOCUMENTED: backend_plan.md §6.5 says only that `relative_level`
 * "may be sent for bar positioning" — it does not commit to a 0–1 input
 * range. The closest real analogue (`ipsatised_mastery_*` in the research
 * dataset) is signed and roughly in [-0.5, 0.5], not [0, 1]. Rather than
 * guess a global scale, this function takes explicit bounds from the caller
 * (see fixtures/authored.ts, which derives them per skill from the real
 * data) and the name says so. Flagged in the Step 3 report — confirm the
 * real API's contract before this ships against a live backend.
 */
export function skillBarPositionFromBounds(
  relativeLevel: number | null,
  bounds: { min: number; max: number },
): number | null {
  if (relativeLevel === null || Number.isNaN(relativeLevel)) return null;
  const { min, max } = bounds;
  if (max <= min) return null;
  const fraction = (relativeLevel - min) / (max - min);
  return Math.min(100, Math.max(0, fraction * 100));
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
//
// Defined here rather than in api/types.ts: docs/13 §2 is read ONLY for what
// a recommendation card must DISPLAY (its storage/state-machine/database
// sections are backend scope, out of bounds for this file). `kind` is a
// loose `string`, not the closed RecommendationKind union — D7 froze the
// action VOCABULARY, not a client-side mapping, and recommendationLabel()
// already has a documented fallback for anything it doesn't recognise.

export interface RecommendationDisplay {
  recommendationId: string;
  kind: string;
  targetSkillDisplayName: string;
  /** ≤280 chars, display-safe — shown WITH the action, never behind a tap. */
  evidenceSummary: string;
  status: "pending" | "accepted" | "dismissed" | "modified";
  /** What the teacher changed it to, when status is "modified". */
  modifiedActionSummary: string | null;
  expiresAfterSession: number;
}

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
