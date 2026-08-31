// Typed stub — fixtures land in Step 3. Every method throws until then.

import type { HomeSummary, SessionEntry } from "../types";
import type {
  ApiClient,
  CohortResponse,
  StudentOverviewResponse,
  WatchListResponse,
} from "../client";

export class MockClient implements ApiClient {
  getHome(): Promise<HomeSummary> {
    throw new Error("not implemented");
  }
  getCohort(_classId: string): Promise<CohortResponse> {
    throw new Error("not implemented");
  }
  getClassWatchList(_classId: string): Promise<WatchListResponse> {
    throw new Error("not implemented");
  }
  getWatchList(): Promise<WatchListResponse> {
    throw new Error("not implemented");
  }
  getStudentOverview(_studentId: string): Promise<StudentOverviewResponse> {
    throw new Error("not implemented");
  }
  getStudentSessions(_studentId: string): Promise<SessionEntry[]> {
    throw new Error("not implemented");
  }
}
