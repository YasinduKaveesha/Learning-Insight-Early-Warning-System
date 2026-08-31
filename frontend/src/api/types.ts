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
  // D17 restricts the SOURCE of any rendered trajectory STATE to
  // practice_accuracy only — see the note on LearnerSnapshot below. The
  // "game_engagement" source value is not removed from the type because a
  // Trajectory shape isn't used for engagement at all any more (there is no
  // engagementTrajectory field left to hold one); it stays here only as a
  // discriminant researchers may reintroduce if D17 is revisited.
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
  // Narrowed to source: "practice_accuracy" (rather than the generic
  // Trajectory) so a component consuming this field is statically incapable
  // of accepting an engagement trajectory here — the D17 restriction is
  // enforced by the type, not just by convention.
  practiceTrajectory: { source: "practice_accuracy"; state: TrajectoryState };
  // D17 (supervisor decision, 2026-08-31): the engagement trajectory STATE
  // (Improving/Stable/Needs Attention derived from c_engagement_score) is
  // withheld from v1. It was computed, audited and held: DD needs_attention
  // lift of 0.76 — inside the band NB07 found for the rejected High tier —
  // and "unknown" for 56-86% of learners because c_engagement_score is
  // missing from ~half of all sessions. Shipping it would under-surface the
  // group the product exists to serve while looking informative. There is
  // deliberately no `engagementTrajectory` field here. The underlying
  // engagement SERIES is retained below (`engagementSparkline`) so a chart
  // can still render it — only the derived three-state chip is withheld.
  // Revisit once the DD subgroup / c_engagement_score coverage issue is
  // resolved and the derived signal is re-audited (plan/docs/11 §5).
  explanation: string | null; // <=280 chars, display names only
  lastActiveDate: string;
  accuracySparkline: number[];
  engagementSparkline: number[];
  modelVersion: string;
  inferenceTimestamp: string;
}

export interface SkillProgress {
  skillId: string; // one of the seven, frozen order
  displayName: string;
  direction: "improving" | "not_moving" | "unknown";
  relativeLevel: number | null; // bar position only — never labelled with a number
  // NOT REAL DATA (Step 3 finding): no per-skill practice-opportunity count
  // exists in the research dataset; this is a placeholder. Kept on the type
  // so a real source can be wired in later, but NO component may render it
  // until one exists — a fabricated count a teacher acts on is worse than no
  // count at all.
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
    // UI-refinement pass: added so Home's class cards can show a
    // pending-join-request indicator without a second round trip.
    pendingRequestCount: number;
  }[];
  disclosure: string; // rendered as-is, never hard-coded
}
