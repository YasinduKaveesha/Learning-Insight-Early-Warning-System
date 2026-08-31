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
  Trajectory,
} from "../../types";
import realSnapshotsAtT7 from "./realSnapshotsAtT7.json";
import rosterStudentIds from "./rosterStudentIds.json";
import skillBoundsAtT7 from "./skillBoundsAtT7.json";
import skillProgressByStudent from "./skillProgressByStudent.json";
import twoSignalExemplar from "./twoSignalExemplarId.json";

export const DISCLOSURE = "Literature-informed synthetic data — not clinical evidence.";
export const TEACHER_NAME = "Ms Perera";

// Real predicted_class/prob_class_* were read and dropped in build-fixtures.mjs
// before this JSON was written — see that script for the audit trail.
type RealSnapshot = Omit<LearnerSnapshot, "displayName" | "classId" | "lastActiveDate" | "modelVersion" | "inferenceTimestamp">;
const REAL_SNAPSHOTS = realSnapshotsAtT7 as unknown as RealSnapshot[];
const REAL_SNAPSHOT_BY_ID = new Map(REAL_SNAPSHOTS.map((s) => [s.studentId, s]));
const ROSTER_IDS = rosterStudentIds as string[];
export const TWO_SIGNAL_EXEMPLAR_ID: string = (twoSignalExemplar as { studentId: string | null })
  .studentId!;

// --- Classes and roster (D2: GRADE_2 / GRADE_3 only) ------------------------

export const CLASSES = [
  { classId: "class-3blue", name: "Grade 3 Blue", grade: "GRADE_3" as const },
  { classId: "class-3green", name: "Grade 3 Green", grade: "GRADE_3" as const },
  { classId: "class-2gold", name: "Grade 2 Gold", grade: "GRADE_2" as const },
];

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

const NO_TRAJECTORY: Trajectory = { source: "practice_accuracy", state: "unknown" };
const NO_ENGAGEMENT_TRAJECTORY: Trajectory = { source: "game_engagement", state: "unknown" };

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
  engagementTrajectory: NO_ENGAGEMENT_TRAJECTORY,
  explanation: null,
  lastActiveDate: authoredDateForSession(1, 1),
  accuracySparkline: [],
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
 * — see NIMAL_SESSIONS_WITH_GAPS below, the one place those two states exist.
 */
export function authoredSessionsFor(studentId: string, sessionsCompleted: number): SessionEntry[] {
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
