import type { QueryClient } from "@tanstack/react-query";
import { client, type ClassStudentOverview } from "../api/client";

/**
 * Background loading, so a teacher does not wait on the hosted database while
 * moving between pages (2026-09-16).
 *
 * Home loads first. Then, quietly and a couple at a time, every class page
 * and every learner in it is fetched and placed in the query cache under the
 * SAME keys the screens already read. Opening a class or a learner then
 * renders from memory immediately.
 *
 * Nothing here shows an error: a prefetch that fails simply leaves that page to
 * load normally when it is opened, with its own loading and error states.
 */

/** How many classes are warmed at once: ONE. Measured 2026-09-16 on a slow
 * connection to the hosted database: two at a time made every request queue
 * behind the others -- Home 12 s, class pages 10-22 s -- while strictly one at
 * a time gave Home 2.7 s and a class 1.6 s. Background work must never slow the
 * page the teacher is looking at. */
export const CLASS_CONCURRENCY = 1;

export const classStudentOverviewsKey = (classId: string) =>
  ["classStudentOverviews", classId] as const;

/** Put each learner where `StudentDetail` looks for them. An entry that
 * already holds data is left alone: it may be fresher than this class read --
 * a decision refetches that learner's suggestions. */
export function seedStudents(queryClient: QueryClient, students: ClassStudentOverview[]) {
  for (const s of students) {
    const overviewKey = ["studentOverview", s.studentId];
    if (queryClient.getQueryData(overviewKey) === undefined) {
      queryClient.setQueryData(overviewKey, s.overview);
    }
    const recommendationsKey = ["studentRecommendations", s.studentId];
    if (queryClient.getQueryData(recommendationsKey) === undefined) {
      queryClient.setQueryData(recommendationsKey, s.recommendations);
    }
  }
}

/** One class's learners, fetched once and seeded into the per-learner caches. */
export async function prefetchClassStudents(queryClient: QueryClient, classId: string) {
  try {
    const students = await queryClient.fetchQuery({
      queryKey: classStudentOverviewsKey(classId),
      queryFn: () => client.getClassStudentOverviews(classId),
    });
    seedStudents(queryClient, students);
  } catch {
    // Background work only -- the page will load on its own when opened.
  }
}

/** One class page and all its learners. */
export async function prefetchClass(queryClient: QueryClient, classId: string) {
  await queryClient.prefetchQuery({
    queryKey: ["cohort", classId],
    queryFn: () => client.getCohort(classId),
  });
  await prefetchClassStudents(queryClient, classId);
}

/** Every class, in the order given (the order Home shows them), a few at a time. */
export async function prefetchClasses(queryClient: QueryClient, classIds: string[]) {
  const queue = [...classIds];
  const worker = async () => {
    for (let id = queue.shift(); id !== undefined; id = queue.shift()) {
      await prefetchClass(queryClient, id);
    }
  };
  await Promise.all(
    Array.from({ length: Math.min(CLASS_CONCURRENCY, queue.length) }, worker),
  );
}
