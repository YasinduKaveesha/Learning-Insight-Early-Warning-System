// THE SEAM. This is the only file that knows whether data is mock or real.
// Swapping to the real FastAPI service changes only this file.

import type { HomeSummary, LearnerSnapshot, SessionEntry, SkillProgress } from "./types";
import type { Grade, PendingRequestDisplay, RecommendationDisplay } from "../lib/presentation";
import { DuplicateClassNameError, isDuplicateClassNameError } from "../lib/presentation";
import { MockClient } from "./mock/mockClient";
import { HttpClient } from "./httpClient";
import { isSupabaseConfigured } from "./supabaseClient";

// Re-exported so a caller can `import { DuplicateClassNameError } from
// "api/client"` alongside the rest of the seam's types, without needing to
// know it's actually defined in lib/presentation.ts (see that file for why).
// Prefer isDuplicateClassNameError(e) over `e instanceof DuplicateClassNameError`
// — see that function's doc comment.
export { DuplicateClassNameError, isDuplicateClassNameError };

export interface CohortResponse {
  classId: string;
  className: string;
  studentCount: number;
  toWatchCount: number;
  gettingStartedCount: number;
  pendingRequestCount: number;
  students: LearnerSnapshot[];
  // Added in Step 5: every analytics surface carries the disclosure fed
  // from the API response (plan §4.1) — the Cohort screen is one, so it
  // needs the field even though Step 3 didn't originally return it here.
  disclosure: string;
  // Added in Step 6, for the Class Info dialog (plan §4.7: "Class name,
  // grade, student count" plus the permanent key) — reached from the
  // classroom screen that already has this response loaded, so no second
  // round trip is needed to populate that dialog.
  grade: Grade;
  classKey: string;
}

/**
 * PROVISIONAL, in the same spirit as CohortResponse's added fields (Step 5)
 * and PendingRequestDisplay (Step 6) — plan §4.6 names the sections a
 * Reports screen must have, but there is no reports endpoint or response
 * spec behind any of it. `earlyWarningTrend` is the unmodified real
 * early-detection curve (56_early_detection_curve.csv, teacher/cohort-wide,
 * not per-class — there is only one real curve, so every class's Reports
 * screen shows the same one, labelled "across the study" rather than
 * falsely scoped to one classroom). `classLearningProgress` and
 * `participation` ARE per-class, derived from that class's own roster
 * fixtures — see fixtures/authored.ts's classReportsFor().
 *
 * REMOVED (Step 8 review): a `studentsToWatchOverTime` field used to exist
 * here, computed by scaling `earlyWarningTrend`'s own flag-rate curve by
 * this class's roster size. On screen that produced two charts on one
 * report — "Students to watch" and "Early-warning trend" — drawn from the
 * SAME underlying series, with nothing telling a teacher that. Two charts
 * that silently agree because they are the same data read as
 * corroborating evidence, which manufactures apparent confidence docs/12
 * §7 forbids ("never falsely confident"). There is no real per-class
 * longitudinal watch-count in any Step 3 artefact — only one current-t
 * snapshot was ever computed — so rather than fabricate or duplicate,
 * plan §4.6's "students to watch over time" section now renders an honest
 * not-enough-history state instead of a chart. See
 * ClassroomReportsRoute.tsx.
 */
export interface ClassReportsResponse {
  disclosure: string;
  className: string;
  // Trend sentences are computed at render time (lib/format.ts's
  // describeTrend), the same pattern StudentRoute uses for its charts — the
  // mock only returns raw derived values, never pre-written prose.
  classLearningProgress: { sessionNumbers: number[]; values: number[] };
  earlyWarningTrend: {
    sessionNumbers: number[];
    flagRates: number[];
    /** The one-line plain-language explanation of what this curve shows —
     * most readers will not have met an early-detection curve before
     * (plan §4.6). Written for a teacher, not a reviewer. */
    explanation: string;
  };
  participation: { bucketLabel: string; studentCount: number }[];
}

export interface CreateClassResult {
  classId: string;
  className: string;
  grade: Grade;
  classKey: string;
}

export interface WatchListResponse {
  totalStudents: number;
  disclosure: string;
  students: LearnerSnapshot[];
}

export interface StudentOverviewResponse {
  snapshot: LearnerSnapshot;
  skills: SkillProgress[];
  // Added in Step 5, for the same reason as CohortResponse.disclosure above.
  disclosure: string;
  // The class name for "Priority N in <class name>" (plan §4.4) — the
  // snapshot only carries classId, and the Student Overview screen has no
  // other endpoint to resolve it from without an extra round trip.
  className: string;
  // Per-skill bar bounds (see skillBarPositionFromBounds's doc comment in
  // lib/presentation.ts) — computed at fixture build time from the real
  // roster, not a documented part of the eventual API contract.
  skillBounds: Record<string, { min: number; max: number }>;
}

export interface ApiClient {
  getHome(): Promise<HomeSummary>;
  getCohort(classId: string): Promise<CohortResponse>;
  getClassWatchList(classId: string): Promise<WatchListResponse>;
  getWatchList(): Promise<WatchListResponse>;
  getStudentOverview(studentId: string): Promise<StudentOverviewResponse>;
  getStudentSessions(studentId: string): Promise<SessionEntry[]>;
  // PROVISIONAL — see the doc comment on RecommendationDisplay in
  // lib/presentation.ts (Step 4 review ruling B, carried forward). Added in
  // Step 5 only because the Student Overview screen's wireframe (plan §4.4)
  // includes a Suggestions section; there is no recommendation endpoint or
  // specification behind this yet.
  getStudentRecommendations(studentId: string): Promise<RecommendationDisplay[]>;

  // --- Step 6: class management --------------------------------------------

  /** Throws DuplicateClassNameError on a name collision (case-insensitive,
   * trimmed, per teacher). Never throws for any other reason a screen would
   * need to distinguish — a network/server failure is a plain Error and
   * renders through the generic ErrorState instead. */
  createClass(name: string, grade: Grade): Promise<CreateClassResult>;

  // PROVISIONAL — see the doc comment on PendingRequestDisplay in
  // lib/presentation.ts. The real join-request flow is owned by the student
  // app's existing endpoints (plan §4.7); these three exist only so the
  // Step 6 screen has something to call through the seam.
  getJoinRequests(classId: string): Promise<PendingRequestDisplay[]>;
  approveJoinRequest(classId: string, requestId: string): Promise<void>;
  rejectJoinRequest(classId: string, requestId: string): Promise<void>;

  // --- Step 7: Reports ------------------------------------------------------

  /** PROVISIONAL — see ClassReportsResponse's doc comment. Never returns a
   * research metric (precision, recall, F1, AUC, lift, calibration, a
   * confusion matrix, or a breakdown by research cohort group) — those are evidence
   * for what the product may do, not content for a teacher (plan §4.6). */
  getClassReports(classId: string): Promise<ClassReportsResponse>;
}

// VITE_USE_MOCK=true, or no Supabase project configured, keeps the whole app
// on MockClient -- the rollback path if the backend is down (frontend_plan
// section 11.0 gate 5). MockClient is deliberately NOT deleted.
export const client: ApiClient = isSupabaseConfigured ? new HttpClient() : new MockClient();
