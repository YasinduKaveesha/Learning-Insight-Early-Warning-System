import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { client } from "../../api/client";
import { ClassInfoDialog } from "../../components/class/ClassInfoDialog";
import { DisclosureFooter } from "../../components/shared/DisclosureFooter";
import { EmptyState } from "../../components/shared/EmptyState";
import { ErrorState } from "../../components/shared/ErrorState";
import { FramingLine } from "../../components/shared/FramingLine";
import { LoadingSkeleton } from "../../components/shared/LoadingSkeleton";
import { SearchField } from "../../components/shared/SearchField";
import { SectionHeader } from "../../components/shared/SectionHeader";
import { StatTile } from "../../components/shared/StatTile";
import { StudentCard } from "../../components/student/StudentCard";
import {
  SNAPSHOT_FRAMING,
  sortCohortOrder,
  type LearnerSnapshot,
  toWatchStatus,
} from "../../lib/presentation";

/**
 * Classroom / Cohort (plan §4.2) — the main working screen. Ordering
 * matters: watched first by priority, then no-current-concern, then
 * Getting Started LAST — never among the no-concern students ("we don't
 * know" and "no concern" are different answers, docs/12 §3).
 *
 * Step 6 fix: this screen no longer trusts the API's order. sortCohortOrder
 * (lib/presentation.ts) is applied here explicitly, in addition to the
 * mock client applying it too — defence in depth, so a future real backend
 * that returns students in a different order cannot silently interleave
 * Getting Started among no-concern students. See that function's doc
 * comment for the regression this closes.
 */
export default function ClassroomRoute() {
  const { classId } = useParams<{ classId: string }>();
  const [search, setSearch] = useState("");
  const [isInfoOpen, setIsInfoOpen] = useState(false);

  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ["cohort", classId],
    queryFn: () => client.getCohort(classId!),
    enabled: !!classId,
  });

  const ordered = useMemo(() => {
    if (!data) return [];
    return sortCohortOrder(data.students);
  }, [data]);

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (query === "") return ordered;
    return ordered.filter((s) => s.displayName.toLowerCase().includes(query));
  }, [ordered, search]);

  const watching = filtered.filter((s) => toWatchStatus(s).kind === "watching");
  // Preserves the order sortCohortOrder produced — no-concern students
  // first, Getting Started last, never interleaved (see doc comment above).
  const allOthers = filtered.filter((s) => toWatchStatus(s).kind !== "watching");

  return (
    <div className="mx-auto flex max-w-[480px] lg:max-w-[1200px] flex-col gap-4 p-4 pb-8">
      {/* Hardening-pass fix: the back link's aria-label was overriding its
          own visible text, so the class name inside it never reached
          assistive tech at all — a screen-reader user heard only "Back to
          classes" with the class name silently dropped. Split into a
          plain back link plus a real h1 (docs/11 §8: "sane heading
          hierarchy") that actually carries the class name. */}
      <header className="flex items-center justify-between gap-2">
        <Link
          to="/classes"
          aria-label="Back to classes"
          className="flex h-11 min-w-[44px] items-center text-sm font-medium text-ink-primary"
        >
          ←
        </Link>
        <h1 className="flex-1 truncate text-base font-semibold text-ink-primary">
          {isPending ? "" : (data?.className ?? "Class")}
        </h1>
        <button
          type="button"
          aria-label="Class info"
          onClick={() => setIsInfoOpen(true)}
          disabled={!data}
          className="flex h-11 w-11 items-center justify-center rounded-full border border-border-strong text-ink-primary disabled:opacity-40"
        >
          ⓘ
        </button>
      </header>
      <FramingLine />

      {data ? (
        <ClassInfoDialog
          isOpen={isInfoOpen}
          onClose={() => setIsInfoOpen(false)}
          className={data.className}
          grade={data.grade}
          classKey={data.classKey}
          studentCount={data.studentCount}
        />
      ) : null}

      {isPending ? (
        <>
          <LoadingSkeleton rows={1} rowHeight={44} />
          <LoadingSkeleton rows={1} rowHeight={72} />
          <LoadingSkeleton rows={4} rowHeight={80} />
        </>
      ) : isError ? (
        <ErrorState
          message="Couldn't load this class. Check your connection and try again."
          onRetry={() => refetch()}
        />
      ) : data.studentCount === 0 ? (
        // The useful empty state is the class key, not "no students" —
        // it's the thing the teacher needs to actually fix this (docs/11
        // §7's own example: "No learners yet. Share the class key ...").
        <EmptyState message={`No students yet. Share the key ${data.classKey}.`} />
      ) : (
        <>
          <SearchField
            label="Search students"
            value={search}
            onChange={setSearch}
            placeholder="Search students..."
            resultCount={filtered.length}
          />

          <div className="grid grid-cols-3 gap-2">
            <StatTile label="Students" value={data.studentCount} />
            <StatTile label="To Watch" value={data.toWatchCount} />
            <StatTile label="Getting Started" value={data.gettingStartedCount} />
          </div>

          {data.pendingRequestCount > 0 ? (
            <Link
              to={`/classes/${classId}/requests`}
              className="flex min-h-[44px] items-center justify-between rounded-lg border border-border bg-surface2 px-3 text-sm text-ink-primary"
            >
              <span>
                ⚑ {data.pendingRequestCount} join request
                {data.pendingRequestCount === 1 ? "" : "s"} pending
              </span>
              <span aria-hidden="true">→</span>
            </Link>
          ) : null}

          <section>
            <SectionHeader title="Students to Watch" subtitle={SNAPSHOT_FRAMING} />
            {watching.length === 0 ? (
              <EmptyState message="No students in this class are currently flagged for review." />
            ) : (
              <StudentCardList students={watching} />
            )}
          </section>

          <section>
            <SectionHeader title="All Students" />
            {allOthers.length === 0 ? (
              <EmptyState message="No other students to show here." />
            ) : (
              <StudentCardList students={allOthers} />
            )}
          </section>

          <DisclosureFooter disclosure={data.disclosure} />
        </>
      )}
    </div>
  );
}

function StudentCardList({ students }: { students: LearnerSnapshot[] }) {
  return (
    <div className="flex flex-col gap-2">
      {students.map((s) => (
        <Link key={s.studentId} to={`/students/${s.studentId}`} className="block">
          <StudentCard snapshot={s} />
        </Link>
      ))}
    </div>
  );
}
