import type { QueryClient } from "@tanstack/react-query";
import { client, type ClassStudentOverview } from "../api/client";
import { sortClassesByWatchShare } from "./presentation";

/**
 * Background loading, so a teacher does not wait on the hosted database while
 * moving between pages (2026-09-16, re-ordered 2026-10-08).
 *
 * Home loads first, on its own. Everything else is warmed behind it, ONE
 * request at a time, into the SAME cache keys the screens already read, so
 * opening a page renders from memory.
 *
 * THE ORDER IS THE WHOLE POINT, and it is breadth-first across classes, not
 * depth-first into one:
 *
 *   TIER 1  every class's own page -- the cohort and the class watch list --
 *           plus the all-classes watch list that Home's biggest card opens.
 *   TIER 2  every class's learners (one request per class, seeded into each
 *           learner's cache).
 *   TIER 3  each learner's session history (one request per learner).
 *
 * The previous version ran all three tiers for ONE class before starting the
 * next, so the second class page queued behind the first class's 20 learners.
 * A teacher who opened their second class waited on learner data they had not
 * asked for. Now no learner is fetched until every class page is in hand, and
 * no session history until every learner is.
 *
 * NAVIGATION OUTRANKS THE PLAN. `prioritiseClass` moves one class's remaining
 * work -- all three tiers of it -- to the front of the queue, keeping their
 * relative order. Open a class a second after signing in and that class is
 * fetched next, its learners after it, and then the original order resumes
 * exactly where it left off. Nothing is re-fetched and nothing is dropped.
 *
 * Nothing here shows an error: a prefetch that fails simply leaves that page to
 * load normally when it is opened, with its own loading and error states.
 */

/** How many requests are in flight at once: ONE. Measured 2026-09-16 on a slow
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

// --- the individual fetches -------------------------------------------------

/** One class's page: the cohort and that class's watch list. */
async function prefetchClassPage(
  queryClient: QueryClient,
  classId: string,
  signal?: AbortSignal,
) {
  await queryClient.prefetchQuery({
    queryKey: ["cohort", classId],
    queryFn: () => client.getCohort(classId, { signal }),
  });
  await queryClient.prefetchQuery({
    queryKey: ["classWatch", classId],
    queryFn: () => client.getClassWatchList(classId, { signal }),
  });
}

/** The all-classes watch list -- what Home's largest card opens. */
async function prefetchWatchList(queryClient: QueryClient, signal?: AbortSignal) {
  await queryClient.prefetchQuery({
    queryKey: ["watch"],
    queryFn: () => client.getWatchList({ signal }),
  });
}

/** One class's learners, fetched once and seeded into the per-learner caches.
 * Resolves to the learner ids, so their session history can be queued next. */
export async function prefetchClassStudents(
  queryClient: QueryClient,
  classId: string,
  signal?: AbortSignal,
): Promise<string[]> {
  try {
    const students = await queryClient.fetchQuery({
      queryKey: classStudentOverviewsKey(classId),
      queryFn: () => client.getClassStudentOverviews(classId, { signal }),
    });
    seedStudents(queryClient, students);
    return students.map((s) => s.studentId);
  } catch {
    // Background work only -- the page will load on its own when opened.
    return [];
  }
}

/** One learner's session history (the /students/:id/sessions screen). */
async function prefetchStudentSessions(
  queryClient: QueryClient,
  studentId: string,
  signal?: AbortSignal,
) {
  await queryClient.prefetchQuery({
    queryKey: ["studentSessions", studentId],
    queryFn: () => client.getStudentSessions(studentId, { signal }),
  });
}

// --- the queue --------------------------------------------------------------

type Tier = 1 | 2 | 3;

interface Task {
  /** Which class this work belongs to -- what `prioritiseClass` matches on.
   * The empty string is work that belongs to no single class. */
  classId: string;
  tier: Tier;
  run: (signal: AbortSignal) => Promise<void>;
}

let queue: Task[] = [];
let draining = false;
/**
 * WHO is holding the warm-up back, by name. A set rather than a boolean
 * because there are several holders and they overlap: the open screen holds it
 * from the moment of navigation until it is idle, `focusClass` holds it while
 * it loads the class being opened, and a test may hold it by hand. With a
 * boolean, whichever one finished first released the others' hold too -- so
 * `focusClass` resuming could let background work in while the screen that
 * triggered it was still loading. The queue runs only when nobody holds it.
 */
const holds = new Set<string>();

/** The hold the open screen takes on navigation (ForegroundPriority). */
export const NAVIGATION_HOLD = "navigation";
/** Whether a plan has been made this session -- see `ensureWarmUp`. */
let planned = false;
/** The task currently running, and the handle that cancels it. */
let inFlight: { task: Task; controller: AbortController } | null = null;
/** Bumped by every start/cancel, so a drain still running for a previous plan
 * (a previous teacher, or a stale class list) stops instead of writing into
 * the new one's cache. */
let generation = 0;

/** Move one class's remaining work to the front, keeping its own tier order.
 * Called when a screen for that class opens. A class with nothing left queued
 * is a no-op -- it is already warm, or already running. */
export function prioritiseClass(classId: string) {
  const mine = queue.filter((t) => t.classId === classId);
  if (mine.length === 0) return;
  queue = [...mine, ...queue.filter((t) => t.classId !== classId)];
}

/** Stop all background loading and forget the plan (sign-out, or a new plan). */
/** Throw away the plan and whatever is running. Does NOT touch holds: who is
 * waiting for a screen to load is independent of which plan is queued. */
function resetPlan() {
  generation += 1;
  queue = [];
  // Nothing to put back -- the plan is being thrown away.
  inFlight?.controller.abort();
  inFlight = null;
  planned = false;
}

/** Stop all background loading and forget the plan AND every hold (sign-out). */
export function cancelBackgroundLoad() {
  resetPlan();
  holds.clear();
}

/**
 * Start the warm-up from WHEREVER the teacher came in.
 *
 * Home plans the warm-up itself, from the class order it is showing. But a
 * teacher who reloads on a deep link -- /classes/:id/requests, say -- never
 * mounts Home, so before this there was no plan at all and nothing was ever
 * warmed. This fetches the class list (a cache hit when Home has already
 * loaded) and plans from it.
 *
 * Idempotent: the first plan wins, so this never competes with Home's.
 */
export async function ensureWarmUp(queryClient: QueryClient) {
  if (planned) return;
  planned = true;
  try {
    const home = await queryClient.fetchQuery({
      queryKey: ["home"],
      queryFn: () => client.getHome(),
    });
    startBackgroundLoad(
      queryClient,
      sortClassesByWatchShare(home.classes).map((c) => c.classId),
    );
  } catch {
    // Leave it unplanned so the next idle moment can try again.
    planned = false;
  }
}

/** True while there is background work left. Exported for tests. */
export function isBackgroundLoading(): boolean {
  return draining;
}

/** True while the queue is held for a screen the teacher is looking at. */
export function isBackgroundPaused(): boolean {
  return holds.size > 0;
}

/** Hold the queue: no NEW background task starts until `resumeBackgroundLoad`.
 * A task already in flight finishes -- it cannot be un-sent -- so the pause
 * takes effect at the next task boundary, not instantly. */
export function pauseBackgroundLoad(reason: string = NAVIGATION_HOLD) {
  holds.add(reason);
  // STOP THE REQUEST THAT IS ALREADY OUT. Refusing to start the NEXT task is
  // not enough: with one request in flight at a time, a class-overviews read
  // against the hosted database can take seconds, and for every one of those
  // seconds it competes with the page the teacher has just opened. The task is
  // put back at the front of the queue, so pausing costs the work nothing --
  // it is re-run from the start when the queue resumes.
  if (inFlight) {
    queue.unshift(inFlight.task);
    inFlight.controller.abort();
    inFlight = null;
  }
}

/** Release ONE holder. The queue restarts only when the last one lets go. */
export function resumeBackgroundLoad(reason: string = NAVIGATION_HOLD) {
  if (!holds.delete(reason)) return;
  if (holds.size > 0) return;
  void drain();
}

/**
 * THE TEACHER'S OWN PAGE COMES FIRST. Called when a class screen opens.
 *
 * Holds the queue, moves this class to the front of it, and loads this class
 * itself -- its page, its watch list, its learners -- with the connection to
 * itself. Only then does the background plan resume where it left off. Open a
 * second class and the same thing happens again.
 *
 * It fetches rather than re-fetches: each call goes through the query cache, so
 * a class the warm-up already reached costs nothing and the pause is momentary.
 * A fetch the screen itself has in flight is de-duplicated by the cache rather
 * than sent twice.
 *
 * WHY A PAUSE AND NOT JUST A RE-ORDER. Re-ordering alone leaves the promoted
 * class behind whatever request is already in flight, and lets the warm-up keep
 * taking a turn between each of this class's own requests -- two in flight at
 * once, which is the arrangement measured at 12 s a page (see
 * CLASS_CONCURRENCY). The teacher is waiting on this screen; nothing else may
 * compete with it.
 */
const FOCUS_HOLD = "focus";

export async function focusClass(queryClient: QueryClient, classId: string) {
  pauseBackgroundLoad(FOCUS_HOLD);
  prioritiseClass(classId);
  try {
    await queryClient.fetchQuery({
      queryKey: ["cohort", classId],
      queryFn: () => client.getCohort(classId),
    });
    await queryClient.fetchQuery({
      queryKey: ["classWatch", classId],
      queryFn: () => client.getClassWatchList(classId),
    });
    await prefetchClassStudents(queryClient, classId);
  } catch {
    // The screen has its own loading and error states; this only decides
    // ORDER. A failure here must still release the queue, below.
  } finally {
    // Releases only ITS OWN hold. If the screen that opened this class is
    // still loading, its navigation hold keeps the queue down.
    resumeBackgroundLoad(FOCUS_HOLD);
  }
}

/** Consumes whatever is in `queue` until it is empty, one task at a time.
 *
 * It is deliberately NOT tied to one plan. `queue` is re-read every pass, so a
 * task that appended to it, a `prioritiseClass` that re-ordered it, and a
 * `startBackgroundLoad` that replaced it wholesale are all picked up by the
 * next pass. An earlier version returned when the generation changed, which
 * left the flag set and the REPLACEMENT plan never started -- a teacher whose
 * class list changed got no warm-up at all until the next reload. */
async function drain() {
  if (draining) return;
  draining = true;
  try {
    while (holds.size === 0) {
      const task = queue.shift();
      if (task === undefined) break;
      const controller = new AbortController();
      inFlight = { task, controller };
      try {
        await task.run(controller.signal);
      } catch {
        // Background work only -- including the abort that `pauseBackgroundLoad`
        // raises, which has already put this task back on the queue.
      } finally {
        // Cleared only if this task is still the current one: a pause during
        // the await has already replaced it with null.
        if (inFlight?.controller === controller) inFlight = null;
      }
    }
  } finally {
    draining = false;
  }
}

/**
 * Plan and start the whole warm-up, in tier order across `classIds` (the order
 * Home shows them). Safe to call again: the new plan replaces the old one.
 */
export function startBackgroundLoad(queryClient: QueryClient, classIds: string[]) {
  // resetPlan, NOT cancelBackgroundLoad: planning a new warm-up must never
  // release the hold a screen currently loading has taken. Home calls this the
  // moment its own data lands, while the rest of Home is still rendering.
  resetPlan();
  planned = true;
  // Captured for the tier-2 tasks below: by the time one of them resolves the
  // plan may have been replaced, and its tier-3 work must not be queued into
  // the new plan.
  const mine = generation;
  if (classIds.length === 0) return;

  const tier1: Task[] = [
    // The all-classes watch list first: it is what Home's biggest card opens,
    // and it is a single request.
    { classId: "", tier: 1, run: (signal: AbortSignal) => prefetchWatchList(queryClient, signal) },
    ...classIds.map((classId) => ({
      classId,
      tier: 1 as Tier,
      run: (signal: AbortSignal) => prefetchClassPage(queryClient, classId, signal),
    })),
  ];

  const tier2: Task[] = classIds.map((classId) => ({
    classId,
    tier: 2 as Tier,
    run: async (signal: AbortSignal) => {
      const studentIds = await prefetchClassStudents(queryClient, classId, signal);
      if (generation !== mine) return;
      // Tier 3 is queued only once its learners are known. Appending keeps the
      // tiering intact: every class's tier-2 task is still ahead of these, and
      // classes reach tier 2 in order, so sessions stay in class order too.
      queue.push(
        ...studentIds.map((studentId) => ({
          classId,
          tier: 3 as Tier,
          run: (signal: AbortSignal) => prefetchStudentSessions(queryClient, studentId, signal),
        })),
      );
    },
  }));

  queue = [...tier1, ...tier2];
  void drain();
}

/** Run the entire plan to completion. Used by tests, and by any caller that
 * wants to await the warm-up rather than let it run behind the screen. */
export async function prefetchClasses(queryClient: QueryClient, classIds: string[]) {
  startBackgroundLoad(queryClient, classIds);
  while (draining) await new Promise((resolve) => setTimeout(resolve, 0));
}
