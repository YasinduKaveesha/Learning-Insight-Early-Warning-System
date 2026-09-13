// Fixture-backed implementation. Every method resolves typed data derived
// from the real ML artefacts plus the hand-authored fixtures — see
// fixtures/authored.ts and scripts/build-fixtures.mjs for provenance.

import type { HomeSummary, LearnerSnapshot, SessionEntry } from "../types";
import type {
  ApiClient,
  ClassReportsResponse,
  CohortResponse,
  CreateClassResult,
  StudentOverviewResponse,
  WatchListResponse,
} from "../client";
import type {
  Grade,
  ModifiedAction,
  PendingRequestDisplay,
  RecommendationDisplay,
} from "../../lib/presentation";
import { filterExplanation, sortCohortOrder, toWatchStatus } from "../../lib/presentation";
import {
  ALL_CLASS_STUDENTS,
  DISCLOSURE,
  GETTING_STARTED_STUDENT_ID,
  ROSTER_SNAPSHOTS,
  SKILL_BOUNDS_AT_T7,
  TEACHER_NAME,
  allClasses,
  approveJoinRequest as approveJoinRequestFixture,
  classReportsFor,
  createClassRecord,
  decideRecommendationFixture,
  joinRequestsForClass,
  pendingRequestCountForClass,
  recommendationsForStudent,
  rejectJoinRequest as rejectJoinRequestFixture,
  sessionsForGettingStarted,
  sessionsForStudent,
  skillProgressFor,
} from "./fixtures/authored";

// Small artificial latency so Step 4's loading skeletons have something real
// to render against on a phone (plan §8: "skeletons matching the final
// layout, not a spinner over an empty page").
const MOCK_LATENCY_MS = 250;
function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), MOCK_LATENCY_MS));
}

function withFilteredExplanation(snapshot: LearnerSnapshot): LearnerSnapshot {
  // Defence in depth (plan §7) — the build-time transform already applies
  // both explanation filters, but every serving path re-applies them so an
  // unfiltered sentence can never reach a component even if a future fixture
  // update forgets to.
  return {
    ...snapshot,
    explanation: filterExplanation(snapshot.explanation, snapshot.watchFlag),
  };
}

function studentsInClass(classId: string): LearnerSnapshot[] {
  return (ALL_CLASS_STUDENTS[classId] ?? []).map(withFilteredExplanation);
}

function allStudents(): LearnerSnapshot[] {
  return Object.values(ALL_CLASS_STUDENTS).flat().map(withFilteredExplanation);
}

// sortCohortOrder lives in lib/presentation.ts now (Step 6 fix) — this mock
// still applies it here as defence in depth (the same pattern
// filterExplanation uses), but it is no longer the only place the order is
// guaranteed. See that function's doc comment for why the mock-only version
// was a latent regression.

function watchedOnly(students: LearnerSnapshot[]): LearnerSnapshot[] {
  return students
    .filter((s) => toWatchStatus(s).kind === "watching")
    .sort((a, b) => {
      const pa = toWatchStatus(a);
      const pb = toWatchStatus(b);
      const priorityA = pa.kind === "watching" ? (pa.priority ?? Infinity) : Infinity;
      const priorityB = pb.kind === "watching" ? (pb.priority ?? Infinity) : Infinity;
      return priorityA - priorityB;
    });
}

export class MockClient implements ApiClient {
  getHome(): Promise<HomeSummary> {
    const all = allStudents();
    const classes = allClasses();
    const classCards = classes.map((c) => {
      const students = studentsInClass(c.classId);
      return {
        classId: c.classId,
        name: c.name,
        grade: c.grade,
        studentCount: students.length,
        toWatchCount: students.filter((s) => toWatchStatus(s).kind === "watching").length,
        // UI-refinement pass: Home's class cards show a pending-request
        // dot — this was already computed per-class for the Classroom
        // screen (pendingRequestCountForClass), just not surfaced here.
        pendingRequestCount: pendingRequestCountForClass(c.classId),
      };
    });
    return delay({
      teacherName: TEACHER_NAME,
      studentsToWatch: all.filter((s) => toWatchStatus(s).kind === "watching").length,
      activeStudents: all.length,
      classCount: classes.length,
      gettingStarted: all.filter((s) => toWatchStatus(s).kind === "getting_started").length,
      classes: classCards,
      disclosure: DISCLOSURE,
    });
  }

  getCohort(classId: string): Promise<CohortResponse> {
    const classInfo = allClasses().find((c) => c.classId === classId);
    // Defence in depth (Step 6 fix) — sortCohortOrder is applied here AND
    // again by ClassroomRoute itself; see that function's doc comment.
    const students = sortCohortOrder(studentsInClass(classId));
    return delay({
      classId,
      className: classInfo?.name ?? classId,
      grade: classInfo?.grade ?? "GRADE_3",
      classKey: classInfo?.classKey ?? "",
      studentCount: students.length,
      toWatchCount: students.filter((s) => toWatchStatus(s).kind === "watching").length,
      gettingStartedCount: students.filter(
        (s) => toWatchStatus(s).kind === "getting_started",
      ).length,
      pendingRequestCount: pendingRequestCountForClass(classId),
      students,
      disclosure: DISCLOSURE,
    });
  }

  getClassWatchList(classId: string): Promise<WatchListResponse> {
    const students = studentsInClass(classId);
    return delay({
      totalStudents: students.length,
      disclosure: DISCLOSURE,
      students: watchedOnly(students),
    });
  }

  getWatchList(): Promise<WatchListResponse> {
    const students = allStudents();
    return delay({
      totalStudents: students.length,
      disclosure: DISCLOSURE,
      students: watchedOnly(students),
    });
  }

  getStudentOverview(studentId: string): Promise<StudentOverviewResponse> {
    const snapshot = allStudents().find((s) => s.studentId === studentId);
    if (!snapshot) throw new Error(`Unknown student: ${studentId}`);
    const classInfo = allClasses().find((c) => c.classId === snapshot.classId);
    return delay({
      snapshot,
      skills: skillProgressFor(studentId),
      disclosure: DISCLOSURE,
      className: classInfo?.name ?? snapshot.classId,
      skillBounds: SKILL_BOUNDS_AT_T7,
    });
  }

  getStudentSessions(studentId: string): Promise<SessionEntry[]> {
    if (studentId === GETTING_STARTED_STUDENT_ID) {
      return delay(sessionsForGettingStarted());
    }
    const snapshot = ROSTER_SNAPSHOTS.find((s) => s.studentId === studentId);
    const sessionsCompleted = snapshot?.sessionsCompleted ?? 0;
    return delay(sessionsForStudent(studentId, sessionsCompleted));
  }

  getStudentRecommendations(studentId: string): Promise<RecommendationDisplay[]> {
    return delay(recommendationsForStudent(studentId));
  }

  // Each wraps the fixture call so a refusal REJECTS rather than throwing
  // synchronously — the real client can only ever reject.
  acceptRecommendation(recommendationId: string): Promise<RecommendationDisplay> {
    return Promise.resolve().then(() =>
      delay(decideRecommendationFixture(recommendationId, "accepted", null)),
    );
  }

  dismissRecommendation(recommendationId: string): Promise<RecommendationDisplay> {
    return Promise.resolve().then(() =>
      delay(decideRecommendationFixture(recommendationId, "dismissed", null)),
    );
  }

  modifyRecommendation(
    recommendationId: string,
    action: ModifiedAction,
  ): Promise<RecommendationDisplay> {
    return Promise.resolve().then(() =>
      delay(decideRecommendationFixture(recommendationId, "modified", action)),
    );
  }

  createClass(name: string, grade: Grade): Promise<CreateClassResult> {
    // createClassRecord throws DuplicateClassNameError (lib/presentation.ts)
    // directly on a collision — nothing to translate here.
    const record = createClassRecord(name, grade);
    return delay({
      classId: record.classId,
      className: record.name,
      grade: record.grade,
      classKey: record.classKey,
    });
  }

  getJoinRequests(classId: string): Promise<PendingRequestDisplay[]> {
    return delay(joinRequestsForClass(classId));
  }

  approveJoinRequest(classId: string, requestId: string): Promise<void> {
    approveJoinRequestFixture(classId, requestId);
    return delay(undefined);
  }

  rejectJoinRequest(classId: string, requestId: string): Promise<void> {
    rejectJoinRequestFixture(classId, requestId);
    return delay(undefined);
  }

  getClassReports(classId: string): Promise<ClassReportsResponse> {
    const classInfo = allClasses().find((c) => c.classId === classId);
    const data = classReportsFor(classId);
    return delay({
      disclosure: DISCLOSURE,
      className: classInfo?.name ?? classId,
      ...data,
    });
  }
}
