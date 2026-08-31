// THE SEAM. This is the only file that knows whether data is mock or real.
// Swapping to the real FastAPI service changes only this file.

import type { HomeSummary, LearnerSnapshot, SessionEntry, SkillProgress } from "./types";
import { MockClient } from "./mock/mockClient";

export interface CohortResponse {
  classId: string;
  className: string;
  studentCount: number;
  toWatchCount: number;
  gettingStartedCount: number;
  pendingRequestCount: number;
  students: LearnerSnapshot[];
}

export interface WatchListResponse {
  totalStudents: number;
  disclosure: string;
  students: LearnerSnapshot[];
}

export interface StudentOverviewResponse {
  snapshot: LearnerSnapshot;
  skills: SkillProgress[];
}

export interface ApiClient {
  getHome(): Promise<HomeSummary>;
  getCohort(classId: string): Promise<CohortResponse>;
  getClassWatchList(classId: string): Promise<WatchListResponse>;
  getWatchList(): Promise<WatchListResponse>;
  getStudentOverview(studentId: string): Promise<StudentOverviewResponse>;
  getStudentSessions(studentId: string): Promise<SessionEntry[]>;
}

// Fixtures land in Step 3; this stub keeps the seam typed and importable now.
// Swapping to the real FastAPI service means changing only this line.
export const client: ApiClient = new MockClient();
