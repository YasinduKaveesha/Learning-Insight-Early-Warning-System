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

/**
 * Watching first by priority, then no-current-concern, then Getting Started
 * LAST — never interleaved among no-concern students ("we don't know" and
 * "no concern" are different answers, docs/12 §3).
 *
 * THIS IS THE CANONICAL ORDERING — a display-layer guarantee, not a mock
 * convenience. It was originally only implemented inside the mock client
 * (Step 3), which meant ClassroomRoute simply trusted whatever order the
 * API returned. That is a latent regression: plan §5 says swapping to the
 * real FastAPI backend changes api/client.ts and nothing else, at which
 * point the mock client's sort is gone entirely, and a backend that returns
 * students in any other order (e.g. by enrolment date) would silently
 * interleave Getting Started among no-concern students — the exact failure
 * docs/12 §3 exists to prevent — and the screen's own tests would keep
 * passing because they only ever exercised the mock.
 *
 * Fix (Step 6): this function is the one place the order is defined, and
 * BOTH the mock client and every screen that renders a cohort apply it —
 * defence in depth, the same pattern filterExplanation already uses for
 * the explanation filters. The mock's own sort staying in place is not
 * redundant: it's what the mock server would do if it were real, and this
 * function is what protects the screen even when a future real server
 * forgets to.
 */
export function sortCohortOrder(students: LearnerSnapshot[]): LearnerSnapshot[] {
  const rank = (s: LearnerSnapshot) => {
    const status = toWatchStatus(s);
    if (status.kind === "watching") return 0;
    if (status.kind === "no_concern") return 1;
    return 2; // getting_started
  };
  return [...students].sort((a, b) => {
    const rankDiff = rank(a) - rank(b);
    if (rankDiff !== 0) return rankDiff;
    const statusA = toWatchStatus(a);
    const statusB = toWatchStatus(b);
    if (
      statusA.kind === "watching" &&
      statusB.kind === "watching" &&
      (statusA.priority !== null || statusB.priority !== null)
    ) {
      // Both-null used to compute Infinity - Infinity = NaN, which makes
      // Array.sort's order undefined. With D39 the real client sends no
      // priority at all, so that was every flagged learner.
      return (statusA.priority ?? Infinity) - (statusB.priority ?? Infinity);
    }
    return a.displayName.localeCompare(b.displayName);
  });
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

// Hardening-pass copy-lint fix: was word-then-arrow ("improving ↑"); plan §6's
// terminology table and every wireframe mockup (§4.2, §4.4) consistently use
// arrow-FIRST ordering ("↑ improving", "↓ needs attention"). Word-first had
// been the rendered form since Step 4 — this brings it into line with the
// contract plan §6 names explicitly.
const TRAJECTORY_STATE_LABEL: Record<Trajectory["state"], string> = {
  improving: "↑ improving",
  stable: "→ stable",
  needs_attention: "↓ needs attention",
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

// UI-refinement pass: bare state word, no arrow, no source prefix — for a
// display context (StudentCard, this pass) that dropped the D13 chip
// entirely for a plainer inline word. This is NOT a substitute for
// trajectoryLabel/practiceTrajectoryLabel, which stay the only entry
// points TrajectoryChip uses and must keep the source prefix (D13).
// Title-cased directly (rather than relying on CSS text-transform, which
// didn't reliably capitalize both words) — UI-refinement pass.
const TRAJECTORY_STATE_WORD: Record<Trajectory["state"], string> = {
  improving: "Improving",
  stable: "Stable",
  needs_attention: "Needs Attention",
  unknown: "Not Enough Data",
};

export function trajectoryStateWord(state: Trajectory["state"]): string {
  return TRAJECTORY_STATE_WORD[state];
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

// --- Recommendations (D7) -------------------------------------------------
//
// Defined here rather than in api/types.ts: docs/13 §2 is read ONLY for what
// a recommendation card must DISPLAY (its storage/state-machine/database
// sections are backend scope, out of bounds for this file). `kind` is a
// loose `string`, not the closed RecommendationKind union — D7 froze the
// action VOCABULARY, not a client-side mapping, and recommendationLabel()
// already has a documented fallback for anything it doesn't recognise.
//
// PROVISIONAL (Step 4 review ruling B, carried into Step 5): this shape was
// inferred from the frontend_plan.md §4.4 mockup, not from an API spec. It
// is good enough to build screens against, but nothing downstream should
// harden around it as if it were confirmed — expect it to change once a
// real /recommendations endpoint exists, and re-check every consumer
// (mockClient, RecommendationCard, StudentRoute) when it does.

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
  /** The skill key the suggestion targets, used to pre-select the skill in
   * the modify form. Optional so hand-authored fixtures need not carry it. */
  targetSkillId?: string | null;
  /** D13 source label. Optional; the card falls back to the practice label. */
  sourceLabel?: string;
}

/** The card's title: the skill when there is one, otherwise the suggestion
 * type -- a watch-list suggestion (D41) names no skill, and a blank title
 * would read as missing data. */
export function recommendationTitle(r: RecommendationDisplay): string {
  return r.targetSkillDisplayName || recommendationLabel(r.kind);
}

/** D13 source label by trigger. `watch_flag` (D41) is raised from recent
 * learning activity overall; `stagnation` (D35) from practice activity. */
export function recommendationSourceLabel(triggerType: string): string {
  return triggerType === "watch_flag" ? SNAPSHOT_FRAMING : SUGGESTION_SOURCE_LABEL;
}

/** The teacher's replacement action, as the backend stores it: a kind plus
 * an optional skill. Never free text (decision on 2026-09-14, option A). */
export interface ModifiedAction {
  kind: string;
  skillId: string | null;
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

/** The four kinds a teacher may choose when MODIFYING a suggestion (D7). The
 * system itself only ever generates `practice` (D35/D36); a teacher may pick
 * any of the four — docs/13 §6: modifications say what the system SHOULD have
 * suggested, so they must be countable, not free text. */
export const RECOMMENDATION_KIND_OPTIONS: { kind: RecommendationKind; label: string }[] = (
  Object.keys(RECOMMENDATION_LABEL) as RecommendationKind[]
).map((kind) => ({ kind, label: RECOMMENDATION_LABEL[kind] }));

/** The seven skills, in their frozen order, with teacher-facing names. One
 * definition, shared by the skill list, the suggestion card and the client. */
export const SKILL_OPTIONS: { skillId: string; displayName: string }[] = [
  { skillId: "counting", displayName: "Counting" },
  { skillId: "number_sense", displayName: "Number sense" },
  { skillId: "place_value", displayName: "Place value" },
  { skillId: "addition", displayName: "Addition" },
  { skillId: "subtraction", displayName: "Subtraction" },
  { skillId: "multiplication", displayName: "Multiplication" },
  { skillId: "division", displayName: "Division" },
];

export function skillDisplayName(skillId: string | null | undefined): string {
  if (!skillId) return "";
  return SKILL_OPTIONS.find((s) => s.skillId === skillId)?.displayName ?? skillId.replace(/_/g, " ");
}

/** What a teacher changed a suggestion to, e.g. "Review · Place value". */
export function modifiedActionSummary(kind: string, skillId: string | null): string {
  const skill = skillDisplayName(skillId);
  return skill ? `${recommendationLabel(kind)} · ${skill}` : recommendationLabel(kind);
}

/** The single line a DECIDED suggestion shows in place of its buttons. A
 * decided suggestion cannot be decided again (the server refuses), so its
 * buttons must not be offered. */
export function recommendationDecisionLine(r: RecommendationDisplay): string | null {
  switch (r.status) {
    case "accepted":
      return "You accepted this suggestion.";
    case "dismissed":
      return "You dismissed this suggestion.";
    case "modified":
      return r.modifiedActionSummary
        ? `You changed this to: ${r.modifiedActionSummary}.`
        : "You changed this suggestion.";
    default:
      return null;
  }
}

/** Thrown when a decision is refused because the suggestion was already
 * decided or has expired. Recognised by `.code`, not `instanceof` — see
 * DuplicateClassNameError for why. */
export class RecommendationConflictError extends Error {
  readonly code = "RECOMMENDATION_CONFLICT" as const;
  readonly reason: string; // "already_decided" | "expired", or a future server reason
  constructor(reason: string) {
    super(`Recommendation decision refused: ${reason}`);
    this.reason = reason;
    this.name = "RecommendationConflictError";
  }
}

export function isRecommendationConflictError(e: unknown): e is RecommendationConflictError {
  return (
    typeof e === "object" &&
    e !== null &&
    "code" in e &&
    (e as { code: unknown }).code === "RECOMMENDATION_CONFLICT"
  );
}

/** Teacher-facing message for a failed decision. Never a raw error string. */
export function recommendationDecisionError(e: unknown): string {
  if (isRecommendationConflictError(e)) {
    return e.reason === "expired"
      ? "This suggestion has expired, so it can no longer be changed."
      : "This suggestion was already decided.";
  }
  return "Couldn't save your decision. Check your connection and try again.";
}

// --- Classes (D1, D2) ------------------------------------------------------

/** Grades are GRADE_2 / GRADE_3 only (D2) — the database constrains it and
 * the study's learners are aged 7–9. The single canonical type so the
 * grade select, the class-key dialogs and the seam all agree on the same
 * closed set — no free text, no other grades. */
export type Grade = "GRADE_2" | "GRADE_3";

export const GRADE_LABEL: Record<Grade, string> = {
  GRADE_2: "Grade 2",
  GRADE_3: "Grade 3",
};

/**
 * Thrown by ApiClient.createClass on a duplicate name (case-insensitive,
 * trimmed, per teacher — backend_plan.md §3). Defined here rather than in
 * api/client.ts to avoid a circular import: fixtures/authored.ts needs to
 * throw it and client.ts needs to type its createClass signature with it,
 * and client.ts already imports MockClient from the fixtures/mock layer —
 * a reverse import from there back into client.ts would cycle. This file
 * has no dependency on either, so both sides can import from here safely.
 * CreateClassDialog never decides what counts as a duplicate; it only
 * renders the message it's given, so this error's `message` IS the inline
 * field error text.
 *
 * Callers should prefer `isDuplicateClassNameError(e)` over `e instanceof
 * DuplicateClassNameError` — this class crosses the fixtures → mock client
 * → seam boundary, and `instanceof` across separately-resolved import
 * specifiers for the same file has proven unreliable in this project's
 * Windows/Vitest environment (two specifiers for the identical module can
 * end up as distinct instances). `code` is a plain string comparison and
 * can't have that problem.
 */
export class DuplicateClassNameError extends Error {
  readonly code = "DUPLICATE_CLASS_NAME" as const;
  constructor(message: string) {
    super(message);
    this.name = "DuplicateClassNameError";
  }
}

/** See DuplicateClassNameError's doc comment for why this checks `code`
 * rather than `instanceof`. */
export function isDuplicateClassNameError(
  e: unknown,
): e is DuplicateClassNameError {
  return (
    typeof e === "object" &&
    e !== null &&
    "code" in e &&
    (e as { code: unknown }).code === "DUPLICATE_CLASS_NAME"
  );
}

// --- Join requests (docs/11 §4) ---------------------------------------------
//
// PROVISIONAL, in the same spirit as RecommendationDisplay (Step 4 review
// ruling B): docs/11 §4 describes the fields a request card shows (name,
// requested date, approve/reject) but there is no endpoint contract behind
// this yet — the real classroom/membership endpoints belong to the student
// app (plan §4.7's "Join — student-facing" note), which Component 3 does
// not reimplement. This shape is good enough to build the screen against.

export interface PendingRequestDisplay {
  requestId: string;
  studentDisplayName: string;
  requestedDate: string;
}

// --- Snapshot framing (plan §1, §6) ---------------------------------------

export const SNAPSHOT_FRAMING = "Based on recent learning activity";

/**
 * The same framing, said with THIS learner's own numbers: "Based on 15 sessions
 * in 2C". Every part comes from the student's own response — the sessions they
 * have completed and the class they are in — so nothing is inferred.
 *
 * docs/12 §133 requires the fixed phrase on any surface showing a PRIORITY; D39
 * withdrew priority numbers, so this card no longer carries one and the fixed
 * wording no longer binds it. It still says what the judgement is based on,
 * which is the rule's purpose. Falls back to the fixed phrase whenever either
 * number is missing — a learner with no sessions, or no class name to scope it
 * to — because "Based on 0 sessions" states a scope that explains nothing.
 */
export function snapshotFraming(sessionsCompleted: number, className: string): string {
  if (!Number.isFinite(sessionsCompleted) || sessionsCompleted < 1 || !className.trim()) {
    return SNAPSHOT_FRAMING;
  }
  const sessions = sessionsCompleted === 1 ? "1 session" : `${sessionsCompleted} sessions`;
  return `Based on ${sessions} in ${className}`;
}

/** D13 source label for a suggestion (ML ruling ANSWERS_TO_APP_TEAM_4 section 3):
 * the only suggestion v1 generates (D35) is raised from Component B practice
 * evidence, and the card says so outside the 280-character summary. */
export const SUGGESTION_SOURCE_LABEL = "Based on practice activity";

// --- Reports (plan §4.6) ---------------------------------------------------

/**
 * The one-line plain-language explanation required beside the early-warning
 * trend (plan §4.6) — most readers will not have met an early-detection
 * curve before. Written for a teacher, not a reviewer: describes what the
 * line means, not how it was computed, and names no metric.
 */
export const EARLY_WARNING_TREND_EXPLANATION =
  "This shows the share of students the system would have flagged for review by each point in the study — it rises as more activity builds up, not because more students are struggling.";

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
