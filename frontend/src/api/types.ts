// Backend shapes only. lib/presentation.ts converts these to display models.
// No component may import from this file directly.
//
// Deliberately absent (plan §5, §7): prob_class_*, predicted_class, the audit-only
// cohort label, the audit-only subtype label, raw feature values, risk_level,
// risk_score, any cluster field. There is no RiskLevel type in this codebase.

export type EvidenceStatus =
  | "sufficient_evidence"
  | "insufficient_exposure"
  | "insufficient_future_evidence"
  | "censored_by_observation_end"
  | "administratively_missing";

export type TrajectoryState = "improving" | "stable" | "needs_attention" | "unknown";

export interface Trajectory {
  // D12 — practice and engagement trajectories are separate, never averaged.
  source: "practice_accuracy" | "game_engagement";
  state: TrajectoryState;
}

export type RecommendationKind = // D7
  "practice" | "review" | "try_again" | "monitor_progress";

export interface LearnerSnapshot {
  studentId: string; // opaque UUID. Never parsed or constructed client-side.
  displayName: string;
  classId: string;
  sessionNumber: number; // owned by B/C (D9)
  watchFlag: boolean;
  rankWithinSnapshot: number | null;
  evidenceStatus: EvidenceStatus;
  sessionsCompleted: number;
  practiceTrajectory: Trajectory;
  engagementTrajectory: Trajectory;
  explanation: string | null; // <=280 chars, display names only
  lastActiveDate: string;
  accuracySparkline: number[];
  modelVersion: string;
  inferenceTimestamp: string;
}

export interface SkillProgress {
  skillId: string; // one of the seven, frozen order
  displayName: string;
  direction: "improving" | "not_moving" | "unknown";
  relativeLevel: number | null; // bar position only — never labelled with a number
  practiceCount: number;
}

export interface SessionEntry {
  sessionNumber: number;
  date: string;
  practice: {
    present: boolean;
    accuracy: number | null;
    pace: "faster" | "typical" | "slower" | null;
    hintsUsed: number | null;
  };
  games: {
    present: boolean;
    dataComplete: boolean; // false => incomplete, never disengaged
    state: string | null;
    stateReason: string | null;
    engagementDriver: string | null;
    frustrationDriver: string | null;
  };
}

export interface HomeSummary {
  teacherName: string;
  studentsToWatch: number;
  activeStudents: number;
  classCount: number;
  gettingStarted: number;
  classes: {
    classId: string;
    name: string;
    grade: "GRADE_2" | "GRADE_3";
    studentCount: number;
    toWatchCount: number;
  }[];
  disclosure: string; // rendered as-is, never hard-coded
}
