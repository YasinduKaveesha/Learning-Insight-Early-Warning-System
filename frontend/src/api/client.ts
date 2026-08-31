// THE SEAM. This is the only file that knows whether data is mock or real.
// Swapping to the real FastAPI service changes only this file.

import type { HomeSummary, LearnerSnapshot, SessionEntry, SkillProgress } from "./types";
import type { RecommendationDisplay } from "../lib/presentation";
import { MockClient } from "./mock/mockClient";

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
}

// Fixtures land in Step 3; this stub keeps the seam typed and importable now.
// Swapping to the real FastAPI service means changing only this line.
export const client: ApiClient = new MockClient();
