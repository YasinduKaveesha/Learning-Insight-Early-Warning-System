// Hand-authored fixtures — classes, display names, and the states the real
// research dataset cannot produce (plan §5, ../../../docs/16 §2):
//   1. A Getting Started student (evidence_status is sufficient_evidence on
//      every real row — see scripts/build-fixtures.mjs's console output).
//   2. A session with no Component C activity.
//   3. A session with incomplete telemetry.
// Also authored: SessionEntry data in general. The research dataset samples
// features only every two sessions (t = 3, 5, 7, ... 19 — verified against
// every CSV under dataset/training and dataset/features) and carries no raw
// per-session Practice/Games telemetry at all (accuracy%, hints, pace, game
// state) — only engineered aggregates. There is no artefact this file could
// transform for SessionEntry rows, so they are authored here rather than
// derived, and flagged as such in the Step 3 report rather than guessed
// silently into looking like real telemetry.

import type {
  EvidenceStatus,
  LearnerSnapshot,
  SessionEntry,
  SkillProgress,
} from "../../types";
import type {
  ModifiedAction,
  PendingRequestDisplay,
  RecommendationDisplay,
} from "../../../lib/presentation";
import {
  DuplicateClassNameError,
  EARLY_WARNING_TREND_EXPLANATION,
  RecommendationConflictError,
  modifiedActionSummary,
  type Grade,
} from "../../../lib/presentation";
import earlyWarningTrendJson from "./earlyWarningTrend.json";
import realSnapshotsAtT7 from "./realSnapshotsAtT7.json";
import rosterStudentIds from "./rosterStudentIds.json";
import skillBoundsAtT7 from "./skillBoundsAtT7.json";
import skillProgressByStudent from "./skillProgressByStudent.json";

export const DISCLOSURE = "Literature-informed synthetic data — not clinical evidence.";
export const TEACHER_NAME = "Ms Perera";

// Real predicted_class/prob_class_* were read and dropped in build-fixtures.mjs
// before this JSON was written — see that script for the audit trail.
type RealSnapshot = Omit<LearnerSnapshot, "displayName" | "classId" | "lastActiveDate" | "modelVersion" | "inferenceTimestamp">;
const REAL_SNAPSHOTS = realSnapshotsAtT7 as unknown as RealSnapshot[];
const REAL_SNAPSHOT_BY_ID = new Map(REAL_SNAPSHOTS.map((s) => [s.studentId, s]));
const ROSTER_IDS = rosterStudentIds as string[];

// --- Classes and roster (D2: GRADE_2 / GRADE_3 only) ------------------------

interface ClassRecord {
  classId: string;
  name: string;
  grade: Grade;
  // Permanent (D1) — assigned once, at creation, and never regenerated.
  // Excludes visually ambiguous characters (0/O, 1/I) so a teacher can read
  // it aloud to a room and a student can type it back correctly, per the
  // constraint documented in backend_plan.md §4.2.
  classKey: string;
}

const SEED_CLASSES: ClassRecord[] = [
  { classId: "class-3blue", name: "Grade 3 Blue", grade: "GRADE_3", classKey: "7K4P92" },
  { classId: "class-3green", name: "Grade 3 Green", grade: "GRADE_3", classKey: "9M3R58" },
  { classId: "class-2gold", name: "Grade 2 Gold", grade: "GRADE_2", classKey: "4T7N26" },
];

// Classes created during this session via CreateClassDialog (Step 6). Mock
// state only — there is no persistence layer, so this resets on reload,
// same as every other in-memory mutation in this mock client.
const CREATED_CLASSES: ClassRecord[] = [];

export function allClasses(): ClassRecord[] {
  return [...SEED_CLASSES, ...CREATED_CLASSES];
}

function classKeyTaken(key: string): boolean {
  return allClasses().some((c) => c.classKey === key);
}

const KEY_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"; // no 0/O, 1/I

function generateClassKey(): string {
  for (let attempt = 0; attempt < 100; attempt++) {
    let key = "";
    for (let i = 0; i < 6; i++) {
      key += KEY_ALPHABET[Math.floor(Math.random() * KEY_ALPHABET.length)];
    }
    // Exclude a run of the same character repeated — hard to read aloud.
    if (/(.)\1{2,}/.test(key)) continue;
    if (!classKeyTaken(key)) return key;
  }
  throw new Error("Could not generate a unique class key");
}

/**
 * Name is required and unique per teacher, case-insensitive and trimmed
 * (backend_plan.md §3). Throws DuplicateClassNameError — see client.ts —
 * on a collision; CreateClassDialog only ever renders the message it's
 * given, so the message text here IS the inline field error.
 */
export function createClassRecord(name: string, grade: Grade): ClassRecord {
  const trimmed = name.trim();
  const isDuplicate = allClasses().some(
    (c) => c.name.trim().toLowerCase() === trimmed.toLowerCase(),
  );
  if (isDuplicate) {
    throw new DuplicateClassNameError(`A class named "${trimmed}" already exists.`);
  }
  const record: ClassRecord = {
    classId: `class-${Date.now()}-${Math.floor(Math.random() * 1000)}`,
    name: trimmed,
    grade,
    classKey: generateClassKey(),
  };
  CREATED_CLASSES.push(record);
  return record;
}

const DISPLAY_NAME: Record<string, string> = {
  "STU-0103": "Kavindu",
  "STU-0001": "Amara",
  "STU-0004": "Nimal",
  "STU-0008": "Kavya",
  "STU-0010": "Sanduni",
  "STU-0012": "Tharindu",
  "STU-0015": "Dilani",
  "STU-0016": "Ruwan",
  "STU-0030": "Chamari",
  "STU-0005": "Isuru",
  "STU-0014": "Malsha",
  "STU-0023": "Chathura",
  "STU-0040": "Nethmi",
  "STU-0049": "Sachini",
  "STU-0057": "Dinuka",
  "STU-0058": "Hasini",
  "STU-0064": "Kasun",
  "STU-0076": "Ishara",
  "STU-0081": "Ravindu",
  "STU-0091": "Anjali",
  "STU-0092": "Yohan",
  "STU-0109": "Vindya",
  "STU-0115": "Sanjaya",
  "STU-0120": "Tehani",
};

const CLASS_ROSTER: Record<string, string[]> = {
  "class-3blue": ROSTER_IDS.slice(0, 8),
  "class-3green": ROSTER_IDS.slice(8, 16),
  "class-2gold": ROSTER_IDS.slice(16, 24),
};

const STUDENT_CLASS: Record<string, string> = Object.fromEntries(
  Object.entries(CLASS_ROSTER).flatMap(([classId, ids]) => ids.map((id) => [id, classId])),
);

// Deterministic authored dates so re-running the app gives stable fixtures.
// The synthetic research dataset carries no calendar dates at all.
const REFERENCE_DATE = new Date("2026-08-31T00:00:00.000Z");
function authoredDateForSession(sessionNumber: number, mostRecentSessionNumber: number): string {
  const daysAgo = (mostRecentSessionNumber - sessionNumber) * 2 + 1;
  const d = new Date(REFERENCE_DATE.getTime() - daysAgo * 24 * 60 * 60 * 1000);
  return d.toISOString();
}

const MODEL_VERSION = "target_a_logreg_armA_v1"; // nb05_primary_logreg_armA.joblib
const INFERENCE_TIMESTAMP = "2026-08-24T06:00:00.000Z";

function toFullSnapshot(real: RealSnapshot, classId: string): LearnerSnapshot {
  return {
    ...real,
    displayName: DISPLAY_NAME[real.studentId] ?? real.studentId,
    classId,
    lastActiveDate: authoredDateForSession(real.sessionNumber, real.sessionNumber),
    modelVersion: MODEL_VERSION,
    inferenceTimestamp: INFERENCE_TIMESTAMP,
  };
}

export const ROSTER_SNAPSHOTS: LearnerSnapshot[] = ROSTER_IDS.map((id) => {
  const real = REAL_SNAPSHOT_BY_ID.get(id);
  if (!real) throw new Error(`No real snapshot found for roster student ${id}`);
  const classId = STUDENT_CLASS[id]!;
  return toFullSnapshot(real, classId);
});

// --- Hand-authored fixture 1: Getting Started -------------------------------

const NO_TRAJECTORY: LearnerSnapshot["practiceTrajectory"] = {
  source: "practice_accuracy",
  state: "unknown",
};

export const GETTING_STARTED_STUDENT_ID = "STU-GS01";

export const GETTING_STARTED_SNAPSHOT: LearnerSnapshot = {
  studentId: GETTING_STARTED_STUDENT_ID,
  displayName: "Nadeesha",
  classId: "class-3blue",
  sessionNumber: 1,
  watchFlag: false,
  rankWithinSnapshot: null,
  evidenceStatus: "insufficient_exposure" satisfies EvidenceStatus,
  sessionsCompleted: 1,
  practiceTrajectory: NO_TRAJECTORY,
  // D17: no engagementTrajectory field on LearnerSnapshot at all.
  explanation: null,
  lastActiveDate: authoredDateForSession(1, 1),
  accuracySparkline: [],
  engagementSparkline: [],
  modelVersion: MODEL_VERSION,
  inferenceTimestamp: INFERENCE_TIMESTAMP,
};

export const ALL_CLASS_STUDENTS: Record<string, LearnerSnapshot[]> = {
  "class-3blue": [
    ...ROSTER_SNAPSHOTS.filter((s) => s.classId === "class-3blue"),
    GETTING_STARTED_SNAPSHOT,
  ],
  "class-3green": ROSTER_SNAPSHOTS.filter((s) => s.classId === "class-3green"),
  "class-2gold": ROSTER_SNAPSHOTS.filter((s) => s.classId === "class-2gold"),
};

// --- Skill progress (real ipsatised_mastery_* + authored practice counts,
// see scripts/build-fixtures.mjs) ------------------------------------------

const SKILL_PROGRESS_BY_STUDENT = skillProgressByStudent as unknown as Record<
  string,
  SkillProgress[]
>;

export const SKILL_BOUNDS_AT_T7 = skillBoundsAtT7 as Record<
  string,
  { min: number; max: number }
>;

export function skillProgressFor(studentId: string): SkillProgress[] {
  if (studentId === GETTING_STARTED_STUDENT_ID) {
    // A first-class state, not empty (plan §8): descriptive data is always
    // available even before there is enough for a watch judgement, but with
    // too few observations for any skill to show a direction.
    return SKILL_PROGRESS_BY_STUDENT["STU-0001"]!.map((s) => ({
      ...s,
      direction: "unknown",
      relativeLevel: null,
      practiceCount: 1,
    }));
  }
  return SKILL_PROGRESS_BY_STUDENT[studentId] ?? [];
}

// --- Hand-authored fixtures 2 & 3: session-history gaps ---------------------
// Deterministic per-student session generator. Numeric values are authored,
// not derived from telemetry (see file header) — bounded to plausible ranges
// so a 375px session card renders sensibly, never intended as real B/C data.

function hashString(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return h;
}

function authoredSession(studentId: string, sessionNumber: number, mostRecent: number): SessionEntry {
  const seed = hashString(`${studentId}|${sessionNumber}`);
  const accuracy = 0.45 + ((seed % 40) / 100);
  const paces: SessionEntry["practice"]["pace"][] = ["faster", "typical", "slower"];
  return {
    sessionNumber,
    date: authoredDateForSession(sessionNumber, mostRecent),
    practice: {
      present: true,
      accuracy: Number(accuracy.toFixed(2)),
      pace: paces[seed % paces.length]!,
      hintsUsed: seed % 5,
    },
    games: {
      present: true,
      dataComplete: true,
      state: "on_target",
      stateReason: null,
      engagementDriver: "completion",
      frustrationDriver: null,
    },
  };
}

/**
 * Generates a student's most recent sessions (up to 5) as plain, normal
 * sessions. Callers needing the two hand-authored gap states splice them in
 * — see sessionsForStudent below, the one place those two states exist.
 * Not exported (hardening pass: was exported with no external consumer) —
 * sessionsForStudent and sessionsForGettingStarted are the public API.
 */
function authoredSessionsFor(studentId: string, sessionsCompleted: number): SessionEntry[] {
  const count = Math.min(sessionsCompleted, 5);
  const start = Math.max(1, sessionsCompleted - count + 1);
  const sessions: SessionEntry[] = [];
  for (let n = start; n <= sessionsCompleted; n++) {
    sessions.push(authoredSession(studentId, n, sessionsCompleted));
  }
  return sessions;
}

/**
 * Nimal (STU-0004) carries the two hand-authored session-history gap states
 * required by plan §5 / docs/16 §2:
 *   - a session with NO Component C activity ("No activity recorded")
 *   - a session with INCOMPLETE telemetry ("Activity data incomplete for
 *     this session") — proving a technical fault never renders as
 *     disengagement (plan §4.5 rule 3).
 */
export function sessionsForStudent(studentId: string, sessionsCompleted: number): SessionEntry[] {
  const sessions = authoredSessionsFor(studentId, sessionsCompleted);
  if (studentId !== "STU-0004" || sessions.length < 2) return sessions;

  const noGamesIndex = sessions.length - 2;
  const incompleteIndex = sessions.length - 1;

  sessions[noGamesIndex] = {
    ...sessions[noGamesIndex]!,
    games: {
      present: false,
      dataComplete: true,
      state: null,
      stateReason: null,
      engagementDriver: null,
      frustrationDriver: null,
    },
  };
  sessions[incompleteIndex] = {
    ...sessions[incompleteIndex]!,
    games: {
      present: true,
      dataComplete: false,
      state: null,
      stateReason: "telemetry_gap",
      engagementDriver: null,
      frustrationDriver: null,
    },
  };
  return sessions;
}

// Getting Started: exactly one session, both components present and normal.
export function sessionsForGettingStarted(): SessionEntry[] {
  return [authoredSession(GETTING_STARTED_STUDENT_ID, 1, 1)];
}

// --- Hand-authored: Suggestions (Student Overview, plan §4.4) ---------------
//
// PROVISIONAL, per Step 4 review ruling B (see RecommendationDisplay's doc
// comment in lib/presentation.ts) — there is no recommendation endpoint or
// dataset behind this. D7 froze the action VOCABULARY (Practice · Review ·
// Try Again · Monitor Progress), not a trigger → action MAPPING — these
// five demo rows are illustrative content for the primary journey, not a
// rule for when a real backend should emit any particular kind.
//
// Reaches all four known kinds plus one deliberately UNRECOGNISED kind
// (Step 7), all on real roster students in Grade 3 Blue so they're walkable
// from one class: Amara (review), Nimal (practice), Kavya (try_again),
// Sanduni (monitor_progress), Tharindu (an invented kind proving the
// RecommendationCard/recommendationLabel fallback renders rather than
// crashing). Every other student gets an empty list — a legitimate "no
// suggestions" state, not a missing-data gap.
const DEMO_RECOMMENDATIONS: Record<string, RecommendationDisplay> = {
  "STU-0001": {
    recommendationId: "demo-rec-review",
    kind: "review",
    targetSkillDisplayName: "Place value",
    evidenceSummary:
      "Subtraction has been practised for four sessions without improvement, and place value is still developing.",
    status: "pending",
    modifiedActionSummary: null,
    expiresAfterSession: 14,
  },
  "STU-0004": {
    recommendationId: "demo-rec-practice",
    kind: "practice",
    targetSkillDisplayName: "Counting",
    evidenceSummary: "Counting has fewer practice attempts than the other skills this month.",
    status: "pending",
    modifiedActionSummary: null,
    expiresAfterSession: 12,
  },
  "STU-0008": {
    recommendationId: "demo-rec-tryagain",
    kind: "try_again",
    targetSkillDisplayName: "Addition",
    evidenceSummary: "The last addition session ended with several unfinished questions.",
    status: "pending",
    modifiedActionSummary: null,
    expiresAfterSession: 10,
  },
  "STU-0010": {
    recommendationId: "demo-rec-monitor",
    kind: "monitor_progress",
    targetSkillDisplayName: "Number sense",
    evidenceSummary: "No change yet — number sense practice is steady and needs another session or two to read.",
    status: "pending",
    modifiedActionSummary: null,
    expiresAfterSession: 15,
  },
  "STU-0012": {
    recommendationId: "demo-rec-unknown-kind",
    kind: "adjust_difficulty", // deliberately unrecognised — see file header
    targetSkillDisplayName: "Multiplication",
    evidenceSummary: "Recent multiplication sessions have been completed quickly with high accuracy.",
    status: "pending",
    modifiedActionSummary: null,
    expiresAfterSession: 11,
  },
};

export function recommendationsForStudent(studentId: string): RecommendationDisplay[] {
  const recommendation = DEMO_RECOMMENDATIONS[studentId];
  return recommendation ? [{ ...recommendation }] : [];
}

/** Mock state only, like CREATED_CLASSES. Mirrors the real state machine:
 * a decision leaves "pending" exactly once, and a second one is refused with
 * the same RecommendationConflictError the real client raises on a 409. */
export function decideRecommendationFixture(
  recommendationId: string,
  status: "accepted" | "dismissed" | "modified",
  action: ModifiedAction | null,
): RecommendationDisplay {
  const entry = Object.values(DEMO_RECOMMENDATIONS).find(
    (r) => r.recommendationId === recommendationId,
  );
  if (!entry) throw new Error(`Unknown recommendation: ${recommendationId}`);
  if (entry.status !== "pending") throw new RecommendationConflictError("already_decided");
  entry.status = status;
  entry.modifiedActionSummary = action ? modifiedActionSummary(action.kind, action.skillId) : null;
  return { ...entry };
}

// --- Hand-authored: Join requests (docs/11 §4, Step 6) ----------------------
//
// PROVISIONAL — see PendingRequestDisplay's doc comment in
// lib/presentation.ts. Seeded only on Grade 3 Blue so the Cohort screen's
// pending-requests banner has something real to demonstrate; every other
// class starts with none, which is the ordinary "nothing pending" state.
// Approve/reject mutate this in-memory list directly — mock state only,
// same caveat as CREATED_CLASSES above.

const PENDING_REQUESTS: Record<string, PendingRequestDisplay[]> = {
  "class-3blue": [
    {
      requestId: "req-1",
      studentDisplayName: "Devni",
      requestedDate: "2026-08-29T09:00:00.000Z",
    },
    {
      requestId: "req-2",
      studentDisplayName: "Sithumi",
      requestedDate: "2026-08-30T09:00:00.000Z",
    },
  ],
};

export function joinRequestsForClass(classId: string): PendingRequestDisplay[] {
  // A copy, not the live array — removeJoinRequest splices the internal
  // array in place, so returning it by reference would let a caller's
  // already-fetched "before" list silently mutate out from under it the
  // moment a request is approved/rejected.
  return [...(PENDING_REQUESTS[classId] ?? [])];
}

export function pendingRequestCountForClass(classId: string): number {
  return joinRequestsForClass(classId).length;
}

function removeJoinRequest(classId: string, requestId: string): void {
  const list = PENDING_REQUESTS[classId];
  if (!list) return;
  const index = list.findIndex((r) => r.requestId === requestId);
  if (index !== -1) list.splice(index, 1);
}

// Approve/reject both just remove the request from the pending list in this
// mock — there is no membership table here to actually add the learner to
// the roster, and D10-style "no write-back" caution applies to inventing
// state a real backend would need to own correctly (e.g. duplicate
// enrolment checks). The UI-level effect (the request disappears, the
// pending count drops) is what Step 6 is scoped to demonstrate.
export function approveJoinRequest(classId: string, requestId: string): void {
  removeJoinRequest(classId, requestId);
}

export function rejectJoinRequest(classId: string, requestId: string): void {
  removeJoinRequest(classId, requestId);
}

// --- Hand-authored: Reports (plan §4.6, Step 7) -----------------------------
//
// See ClassReportsResponse's doc comment in api/client.ts for what is real
// vs. derived here. Never computes or stores precision, recall, F1, AUC,
// lift, calibration, a confusion matrix, or any breakdown by research cohort group —
// those are evidence for what the product may do, not content for a
// teacher (plan §4.6), and nothing in this codebase has ever needed them
// since Step 3 dropped every probability column at the source.

interface EarlyWarningPoint {
  sessionNumber: number;
  flagRate: number;
  sampleSize: number;
}
const EARLY_WARNING_TREND = earlyWarningTrendJson as EarlyWarningPoint[];

const PARTICIPATION_BUCKETS = [
  { bucketLabel: "1–2 sessions", min: 1, max: 2 },
  { bucketLabel: "3–5 sessions", min: 3, max: 5 },
  { bucketLabel: "6+ sessions", min: 6, max: Infinity },
];

export interface ClassReportsData {
  classLearningProgress: { sessionNumbers: number[]; values: number[] };
  earlyWarningTrend: { sessionNumbers: number[]; flagRates: number[]; explanation: string };
  participation: { bucketLabel: string; studentCount: number }[];
}

export function classReportsFor(classId: string): ClassReportsData {
  const roster = ALL_CLASS_STUDENTS[classId] ?? [];

  // Class learning progress: the class's own real per-student accuracy
  // series (score_avg_recent, see scripts/build-fixtures.mjs), averaged
  // index-aligned across the roster's trailing sessions. Real numbers,
  // averaged — not a fabricated trend.
  const maxLen = Math.max(0, ...roster.map((s) => s.accuracySparkline.length));
  const progressValues: number[] = [];
  for (let i = 0; i < maxLen; i++) {
    const valuesAtIndex = roster
      .map((s) => {
        const offset = maxLen - s.accuracySparkline.length;
        return i >= offset ? s.accuracySparkline[i - offset] : undefined;
      })
      .filter((v): v is number => v !== undefined);
    if (valuesAtIndex.length > 0) {
      progressValues.push(valuesAtIndex.reduce((a, b) => a + b, 0) / valuesAtIndex.length);
    }
  }

  // Participation: a real histogram of this class's own sessionsCompleted —
  // not derived from anything approximate.
  const participation = PARTICIPATION_BUCKETS.map((b) => ({
    bucketLabel: b.bucketLabel,
    studentCount: roster.filter((s) => s.sessionsCompleted >= b.min && s.sessionsCompleted <= b.max)
      .length,
  }));

  // "Students to watch over time" (plan §4.6) is NOT computed here (Step 8
  // review): there is no real per-class longitudinal watch-count in any
  // Step 3 artefact — only one current-t snapshot per class was ever
  // computed. A prior version of this function scaled the early-warning
  // curve by roster size to fill that gap; that produced two charts on one
  // screen drawn from the same series, which reads as corroborating
  // evidence it isn't (docs/12 §7: never falsely confident). See
  // ClassReportsResponse's doc comment in api/client.ts. The route renders
  // an honest "not enough history yet" state for that section instead.

  return {
    classLearningProgress: {
      sessionNumbers: progressValues.map((_, i) => i + 1),
      values: progressValues,
    },
    earlyWarningTrend: {
      sessionNumbers: EARLY_WARNING_TREND.map((p) => p.sessionNumber),
      flagRates: EARLY_WARNING_TREND.map((p) => p.flagRate),
      explanation: EARLY_WARNING_TREND_EXPLANATION,
    },
    participation,
  };
}
