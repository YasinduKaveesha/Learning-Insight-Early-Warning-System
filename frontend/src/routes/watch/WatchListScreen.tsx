import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, House } from "lucide-react";
import { useEffect } from "react";
import { Link } from "react-router-dom";
import { client } from "../../api/client";
import { EmptyState } from "../../components/shared/EmptyState";
import { ErrorState } from "../../components/shared/ErrorState";
import { WatchListSkeleton } from "../../components/skeletons/PageSkeletons";
import { StudentDetail } from "../../components/student/StudentDetail";
import { ExplanationBlock } from "../../components/student/ExplanationBlock";
import { lastActiveLabel } from "../../lib/format";
import { focusClass } from "../../lib/prefetch";
import { handledNote } from "../../lib/presentation";
import { IS_DESKTOP_QUERY, useMediaQuery } from "../../lib/useMediaQuery";
import { type Grade, type LearnerSnapshot } from "../../lib/presentation";

// Same grade -> colour mapping as Home's class cards, so the two screens
// agree with each other. Undefined (grade not yet known/resolved) falls
// back to the original neutral surface1 card.
const GRADE_TONE_CLASSES: Record<Grade, string> = {
  GRADE_2: "border-toneCard-blue-border bg-toneCard-blue-bg text-white",
  GRADE_3: "border-toneCard-green-border bg-toneCard-green-bg text-white",
};

// The class-name pill's own background — the card's fill is the solid
// grade colour, so the pill uses the darker foreground shade of the same
// hue (with white text) to stay visible on top of it.
const GRADE_PILL_CLASSES: Record<Grade, string> = {
  GRADE_2: "bg-watch-watching-fg text-white",
  GRADE_3: "bg-watch-noConcern-fg text-white",
};

interface ClassInfo {
  grade: Grade;
  name: string;
}

export interface WatchListScreenProps {
  /** Omitted for the teacher-wide /watch route (grouped by class). Set for
   * the per-class /classes/:classId/watch route (a single, ungrouped list
   * already scoped to that class). */
  classId?: string;
  /** The student selected in the URL (`/watch/:studentId` or
   * `/classes/:classId/watch/:studentId`) — drives the >=1024px
   * master-detail right pane (plan §8, hardening-pass gap 2). Undefined
   * below 1024px, where the route has no student segment at all: list
   * items there link straight to the standalone `/students/:studentId`
   * route instead, unchanged from before. */
  selectedStudentId?: string;
}

/**
 * One component, two variants (plan §4.3): teacher-wide, grouped by class,
 * and per-class. THE EXPLANATION IS ON THE CARD, NOT BEHIND A TAP — it is
 * what makes the flag actionable rather than oracular. Getting Started
 * students are excluded entirely (they never carry a watchFlag), and
 * "Priority N" only ever appears inside this list.
 *
 * At >=1024px (plan §8) the list sits alongside the selected student's
 * detail, selection driven entirely by the URL so a deep link and the
 * back button both behave correctly. Below 1024px the layout and
 * navigation are unchanged: tapping a card goes to `/students/:id`.
 */
export function WatchListScreen({ classId, selectedStudentId }: WatchListScreenProps) {
  const isDesktop = useMediaQuery(IS_DESKTOP_QUERY);
  const watchQuery = useQuery({
    queryKey: classId ? ["classWatch", classId] : ["watch"],
    queryFn: () => (classId ? client.getClassWatchList(classId) : client.getWatchList()),
  });

  // Only the teacher-wide variant needs class names (and grades, for the
  // per-grade card colour) to group by — the per-class variant is already
  // scoped, so this query is skipped there.
  const homeQuery = useQuery({
    queryKey: ["home"],
    queryFn: () => client.getHome(),
    enabled: !classId,
  });

  // The per-class variant needs its own class's grade for the same card
  // colour — cohort already carries it.
  const cohortQuery = useQuery({
    queryKey: ["cohort", classId],
    queryFn: () => client.getCohort(classId!),
    enabled: !!classId,
  });

  // A class's own watch list is one of that class's pages, so opening it holds
  // the warm-up and loads this class first (see lib/prefetch.ts). The
  // teacher-wide variant belongs to no class and holds nothing.
  const queryClient = useQueryClient();
  useEffect(() => {
    if (classId) void focusClass(queryClient, classId);
  }, [classId, queryClient]);

  const isPending = watchQuery.isPending || (!classId && homeQuery.isPending);
  const isError = watchQuery.isError || (!classId && homeQuery.isError);

  return (
    <div className="mx-auto flex max-w-[480px] flex-col gap-4 p-4 pb-8 lg:max-w-[1200px] lg:flex-row lg:items-start lg:gap-6">
      <div className="flex flex-1 flex-col gap-4 lg:max-w-[420px]">
        {/* PINNED: the header, and with it the Home/Back button, stays at the
            top while the watch list scrolls (explicit direction, 2026-09-14).
            -mx-4 -mt-4 stretch its page-coloured background over the column
            padding so cards disappear beneath it cleanly. */}
        <header className="sticky top-0 z-20 -mx-4 -mt-4 flex items-center gap-2 bg-background px-4 pb-2 pt-4">
          {/* Back-navigation icon convention (going forward): the arrow
              means "back", so it should never point somewhere that isn't
              actually back — when the destination IS Home, show the Home
              icon instead of an arrow that would be misleading there. */}
          <Link
            to={classId ? `/classes/${classId}` : "/"}
            aria-label={classId ? "Back" : "Home"}
            className="flex h-11 w-11 items-center justify-center rounded-full border border-border-strong text-ink-primary"
          >
            {classId ? (
              <ArrowLeft aria-hidden="true" size={22} />
            ) : (
              <House aria-hidden="true" size={22} />
            )}
          </Link>
          {/* UI-refinement pass: the visible title, framing line, and
              count/proportion lines are removed at explicit direction —
              the h1 stays for screen readers only (sr-only) so the page
              keeps its heading landmark (docs/11 §8). */}
          <h1 className="sr-only">Students to Watch</h1>
        </header>

        {isPending ? (
          <WatchListSkeleton />
        ) : isError ? (
          <ErrorState
            message="Couldn't load the watch list. Check your connection and try again."
            onRetry={() => {
              void watchQuery.refetch();
              if (!classId) void homeQuery.refetch();
            }}
          />
        ) : (
          <>
            {watchQuery.data!.students.length === 0 ? (
              <EmptyState message="No students are currently flagged for review." />
            ) : classId ? (
              <FlatWatchList
                students={watchQuery.data!.students}
                classId={classId}
                classInfo={
                  cohortQuery.data
                    ? { grade: cohortQuery.data.grade, name: cohortQuery.data.className }
                    : undefined
                }
                isDesktop={isDesktop}
              />
            ) : (
              <GroupedWatchList
                students={watchQuery.data!.students}
                classInfos={
                  new Map(homeQuery.data!.classes.map((c) => [c.classId, { grade: c.grade, name: c.name }]))
                }
                isDesktop={isDesktop}
              />
            )}

            {/* The "Literature-informed synthetic data — not clinical evidence."
                footer was removed from this page at explicit direction,
                2026-09-14. It is still returned by the API on every response. */}
          </>
        )}
      </div>

      {/* >=1024px master-detail pane (plan §8). Hidden entirely below that
          width — display:none, not just visually collapsed — so it adds no
          height and the mobile layout is unchanged. */}
      <div className="hidden lg:block lg:flex-1">
        {selectedStudentId ? (
          <StudentDetail studentId={selectedStudentId} showSessionsTab={false} />
        ) : (
          <div className="p-4">
            <EmptyState message="Select a student from the list to see their detail." />
          </div>
        )}
      </div>
    </div>
  );
}

function FlatWatchList({
  students,
  classId,
  classInfo,
  isDesktop,
}: {
  students: LearnerSnapshot[];
  classId?: string;
  classInfo?: ClassInfo;
  isDesktop: boolean;
}) {
  return (
    <div className="flex flex-col gap-3">
      {students.map((s) => (
        <WatchCard
          key={s.studentId}
          snapshot={s}
          classId={classId}
          classInfo={classInfo}
          isDesktop={isDesktop}
        />
      ))}
    </div>
  );
}

function GroupedWatchList({
  students,
  classInfos,
  isDesktop,
}: {
  students: LearnerSnapshot[];
  classInfos: Map<string, ClassInfo>;
  isDesktop: boolean;
}) {
  // UI-refinement pass: the class-name heading between groups is removed —
  // each card now carries its own grade colour AND a grade/class-name line
  // (same blue/green as Home) instead of a section heading. Grouping by
  // class still determines card ORDER, just not a visible section break.
  return (
    <div className="flex flex-col gap-3">
      {students.map((s) => (
        <WatchCard
          key={s.studentId}
          snapshot={s}
          classInfo={classInfos.get(s.classId)}
          isDesktop={isDesktop}
        />
      ))}
    </div>
  );
}

function WatchCard({
  snapshot,
  classId,
  classInfo,
  isDesktop,
}: {
  snapshot: LearnerSnapshot;
  classId?: string;
  classInfo?: ClassInfo;
  isDesktop: boolean;
}) {
  // Below 1024px there is no detail pane, so the card goes straight to the
  // standalone student route — unchanged from before this gap was closed.
  // At >=1024px it instead selects the student IN THIS LIST via the URL,
  // so the right-hand pane updates and the selection is deep-linkable.
  const to = isDesktop
    ? classId
      ? `/classes/${classId}/watch/${snapshot.studentId}`
      : `/watch/${snapshot.studentId}`
    : `/students/${snapshot.studentId}`;
  const toneClasses = classInfo ? GRADE_TONE_CLASSES[classInfo.grade] : "border-border bg-surface1";
  // White text only on a solid grade colour; the neutral fallback card keeps dark ink.
  const onColor = classInfo !== undefined;
  // UI-refinement pass: every card the same height regardless of how long
  // its explanation is — a fixed min-height plus a 3-line clamp on the
  // explanation (below) together keep the layout from growing per-card.
  return (
    <Link to={to} className={`flex min-h-[220px] flex-col gap-2 rounded-lg border p-4 ${toneClasses}`}>
      {/* UI-refinement pass: the "Worth watching right now" status badge is
          removed entirely — replaced by just the class name, top-right. */}
      <div className="flex items-start justify-between gap-2">
        <span className={`text-[17px] font-bold ${onColor ? "text-white" : "text-ink-primary"}`}>{snapshot.displayName}</span>
        {classInfo ? (
          <span
            className={`flex items-center justify-center rounded-full px-3 py-1 text-center text-[15px] font-medium ${GRADE_PILL_CLASSES[classInfo.grade]}`}
          >
            {classInfo.name}
          </span>
        ) : null}
      </div>
      <div className="mt-2">
        <ExplanationBlock explanation={snapshot.explanation} showHeading={false} clampLines={3} onColor={onColor} />
      </div>
      <p className={`mt-2 text-sm ${onColor ? "font-semibold text-white" : "text-ink-secondary"}`}>
        {lastActiveLabel(snapshot.lastActiveDate)}
      </p>
      {/* Decision B: the watch list still lists every flagged learner (the count
          is unchanged), and says which ones the teacher has already acted on. */}
      {handledNote(snapshot) ? (
        <p className={`mt-1 text-sm font-semibold ${onColor ? "text-white" : "text-watch-watching-fg"}`}>{handledNote(snapshot)}</p>
      ) : null}
    </Link>
  );
}
