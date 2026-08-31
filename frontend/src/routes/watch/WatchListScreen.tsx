import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { client } from "../../api/client";
import { DisclosureFooter } from "../../components/shared/DisclosureFooter";
import { EmptyState } from "../../components/shared/EmptyState";
import { ErrorState } from "../../components/shared/ErrorState";
import { FramingLine } from "../../components/shared/FramingLine";
import { LoadingSkeleton } from "../../components/shared/LoadingSkeleton";
import { StudentDetail } from "../../components/student/StudentDetail";
import { ExplanationBlock } from "../../components/student/ExplanationBlock";
import { PriorityBadge } from "../../components/status/PriorityBadge";
import { WatchStatusBadge } from "../../components/status/WatchStatusBadge";
import { formatRelativeDate } from "../../lib/format";
import { IS_DESKTOP_QUERY, useMediaQuery } from "../../lib/useMediaQuery";
import { SNAPSHOT_FRAMING, toWatchStatus, type LearnerSnapshot } from "../../lib/presentation";

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

  // Only the teacher-wide variant needs class names to group by — the
  // per-class variant is already scoped, so this query is skipped there.
  const homeQuery = useQuery({
    queryKey: ["home"],
    queryFn: () => client.getHome(),
    enabled: !classId,
  });

  const isPending = watchQuery.isPending || (!classId && homeQuery.isPending);
  const isError = watchQuery.isError || (!classId && homeQuery.isError);

  return (
    <div className="mx-auto flex max-w-[480px] flex-col gap-4 p-4 pb-8 lg:max-w-[1200px] lg:flex-row lg:items-start lg:gap-6">
      <div className="flex flex-1 flex-col gap-4 lg:max-w-[420px]">
        <header className="flex items-center gap-2">
          <Link
            to={classId ? `/classes/${classId}` : "/"}
            aria-label="Back"
            className="flex h-11 min-w-[44px] items-center text-sm font-medium text-ink-primary"
          >
            ←
          </Link>
          <h1 className="text-base font-semibold text-ink-primary">Students to Watch</h1>
        </header>
        <FramingLine />

        {isPending ? (
          <LoadingSkeleton rows={4} rowHeight={140} />
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
            <p className="text-sm text-ink-secondary">
              {watchQuery.data!.students.length} of {watchQuery.data!.totalStudents} students
            </p>
            <p className="text-xs text-ink-secondary">{SNAPSHOT_FRAMING}</p>

            {watchQuery.data!.students.length === 0 ? (
              <EmptyState message="No students are currently flagged for review." />
            ) : classId ? (
              <FlatWatchList students={watchQuery.data!.students} classId={classId} isDesktop={isDesktop} />
            ) : (
              <GroupedWatchList
                students={watchQuery.data!.students}
                classNames={new Map(homeQuery.data!.classes.map((c) => [c.classId, c.name]))}
                isDesktop={isDesktop}
              />
            )}

            <DisclosureFooter disclosure={watchQuery.data!.disclosure} />
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
  isDesktop,
}: {
  students: LearnerSnapshot[];
  classId?: string;
  isDesktop: boolean;
}) {
  return (
    <div className="flex flex-col gap-3">
      {students.map((s) => (
        <WatchCard key={s.studentId} snapshot={s} classId={classId} isDesktop={isDesktop} />
      ))}
    </div>
  );
}

function GroupedWatchList({
  students,
  classNames,
  isDesktop,
}: {
  students: LearnerSnapshot[];
  classNames: Map<string, string>;
  isDesktop: boolean;
}) {
  const byClass = new Map<string, LearnerSnapshot[]>();
  for (const s of students) {
    const group = byClass.get(s.classId) ?? [];
    group.push(s);
    byClass.set(s.classId, group);
  }
  return (
    <div className="flex flex-col gap-4">
      {Array.from(byClass.entries()).map(([classId, group]) => (
        <div key={classId} className="flex flex-col gap-2">
          <h2 className="px-1 text-sm font-semibold text-ink-primary">
            {classNames.get(classId) ?? classId}
          </h2>
          <div className="flex flex-col gap-3">
            {group.map((s) => (
              // The teacher-wide list is never itself scoped to a class, so
              // its desktop selection link is always /watch/:studentId,
              // even though each card here belongs to a class group.
              <WatchCard key={s.studentId} snapshot={s} isDesktop={isDesktop} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function WatchCard({
  snapshot,
  classId,
  isDesktop,
}: {
  snapshot: LearnerSnapshot;
  classId?: string;
  isDesktop: boolean;
}) {
  const status = toWatchStatus(snapshot);
  const priority = status.kind === "watching" ? status.priority : null;
  // Below 1024px there is no detail pane, so the card goes straight to the
  // standalone student route — unchanged from before this gap was closed.
  // At >=1024px it instead selects the student IN THIS LIST via the URL,
  // so the right-hand pane updates and the selection is deep-linkable.
  const to = isDesktop
    ? classId
      ? `/classes/${classId}/watch/${snapshot.studentId}`
      : `/watch/${snapshot.studentId}`
    : `/students/${snapshot.studentId}`;
  return (
    <Link
      to={to}
      className="flex flex-col gap-2 rounded-lg border border-border bg-surface1 p-4"
    >
      {priority !== null ? <PriorityBadge priority={priority} /> : null}
      <div className="mt-1 flex items-center justify-between gap-2">
        <span className="text-sm font-semibold text-ink-primary">{snapshot.displayName}</span>
        <WatchStatusBadge status={status} />
      </div>
      <div className="mt-2">
        <ExplanationBlock explanation={snapshot.explanation} />
      </div>
      <p className="mt-2 text-xs text-ink-secondary">
        Last active {formatRelativeDate(snapshot.lastActiveDate)}
      </p>
    </Link>
  );
}
