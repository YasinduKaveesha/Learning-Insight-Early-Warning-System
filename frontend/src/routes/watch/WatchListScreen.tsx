import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { client } from "../../api/client";
import { DisclosureFooter } from "../../components/shared/DisclosureFooter";
import { EmptyState } from "../../components/shared/EmptyState";
import { ErrorState } from "../../components/shared/ErrorState";
import { FramingLine } from "../../components/shared/FramingLine";
import { LoadingSkeleton } from "../../components/shared/LoadingSkeleton";
import { ExplanationBlock } from "../../components/student/ExplanationBlock";
import { PriorityBadge } from "../../components/status/PriorityBadge";
import { WatchStatusBadge } from "../../components/status/WatchStatusBadge";
import { formatRelativeDate } from "../../lib/format";
import { SNAPSHOT_FRAMING, toWatchStatus, type LearnerSnapshot } from "../../lib/presentation";

export interface WatchListScreenProps {
  /** Omitted for the teacher-wide /watch route (grouped by class). Set for
   * the per-class /classes/:classId/watch route (a single, ungrouped list
   * already scoped to that class). */
  classId?: string;
}

/**
 * One component, two variants (plan §4.3): teacher-wide, grouped by class,
 * and per-class. THE EXPLANATION IS ON THE CARD, NOT BEHIND A TAP — it is
 * what makes the flag actionable rather than oracular. Getting Started
 * students are excluded entirely (they never carry a watchFlag), and
 * "Priority N" only ever appears inside this list.
 */
export function WatchListScreen({ classId }: WatchListScreenProps) {
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
    <div className="mx-auto flex max-w-[480px] flex-col gap-4 p-4 pb-8">
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
            <FlatWatchList students={watchQuery.data!.students} />
          ) : (
            <GroupedWatchList
              students={watchQuery.data!.students}
              classNames={new Map(homeQuery.data!.classes.map((c) => [c.classId, c.name]))}
            />
          )}

          <DisclosureFooter disclosure={watchQuery.data!.disclosure} />
        </>
      )}
    </div>
  );
}

function FlatWatchList({ students }: { students: LearnerSnapshot[] }) {
  return (
    <div className="flex flex-col gap-3">
      {students.map((s) => (
        <WatchCard key={s.studentId} snapshot={s} />
      ))}
    </div>
  );
}

function GroupedWatchList({
  students,
  classNames,
}: {
  students: LearnerSnapshot[];
  classNames: Map<string, string>;
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
              <WatchCard key={s.studentId} snapshot={s} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function WatchCard({ snapshot }: { snapshot: LearnerSnapshot }) {
  const status = toWatchStatus(snapshot);
  const priority = status.kind === "watching" ? status.priority : null;
  return (
    <Link
      to={`/students/${snapshot.studentId}`}
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
