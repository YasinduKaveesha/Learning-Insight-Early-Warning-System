// Fixture-backed implementation. Every method resolves typed data derived
// from the real ML artefacts plus the hand-authored fixtures — see
// fixtures/authored.ts and scripts/build-fixtures.mjs for provenance.

import type { HomeSummary, LearnerSnapshot, SessionEntry } from "../types";
import type {
  ApiClient,
  CohortResponse,
  StudentOverviewResponse,
  WatchListResponse,
} from "../client";
import type { RecommendationDisplay } from "../../lib/presentation";
import { filterExplanation, toWatchStatus } from "../../lib/presentation";
import {
  ALL_CLASS_STUDENTS,
  CLASSES,
  DISCLOSURE,
  GETTING_STARTED_STUDENT_ID,
  recommendationsForStudent,
  ROSTER_SNAPSHOTS,
  SKILL_BOUNDS_AT_T7,
  TEACHER_NAME,
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

/**
 * Watching first by priority, then no concern, then Getting Started last —
 * never sorted among no-concern students (plan §4.2: "we don't know" and "no
 * concern" are different answers, and merging them is the failure the whole
 * nullable design exists to prevent).
 */
function sortCohortOrder(students: LearnerSnapshot[]): LearnerSnapshot[] {
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
    if (statusA.kind === "watching" && statusB.kind === "watching") {
      return (statusA.priority ?? Infinity) - (statusB.priority ?? Infinity);
    }
    return a.displayName.localeCompare(b.displayName);
  });
}

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
    const classCards = CLASSES.map((c) => {
      const students = studentsInClass(c.classId);
      return {
        classId: c.classId,
        name: c.name,
        grade: c.grade,
        studentCount: students.length,
        toWatchCount: students.filter((s) => toWatchStatus(s).kind === "watching").length,
      };
    });
    return delay({
      teacherName: TEACHER_NAME,
      studentsToWatch: all.filter((s) => toWatchStatus(s).kind === "watching").length,
      activeStudents: all.length,
      classCount: CLASSES.length,
      gettingStarted: all.filter((s) => toWatchStatus(s).kind === "getting_started").length,
      classes: classCards,
      disclosure: DISCLOSURE,
    });
  }

  getCohort(classId: string): Promise<CohortResponse> {
    const classInfo = CLASSES.find((c) => c.classId === classId);
    const students = sortCohortOrder(studentsInClass(classId));
    return delay({
      classId,
      className: classInfo?.name ?? classId,
      studentCount: students.length,
      toWatchCount: students.filter((s) => toWatchStatus(s).kind === "watching").length,
      gettingStartedCount: students.filter(
        (s) => toWatchStatus(s).kind === "getting_started",
      ).length,
      pendingRequestCount: 0,
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
    const classInfo = CLASSES.find((c) => c.classId === snapshot.classId);
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
}
