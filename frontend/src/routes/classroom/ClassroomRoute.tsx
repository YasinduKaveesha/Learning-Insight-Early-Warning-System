import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { client } from "../../api/client";
import { DisclosureFooter } from "../../components/shared/DisclosureFooter";
import { EmptyState } from "../../components/shared/EmptyState";
import { ErrorState } from "../../components/shared/ErrorState";
import { FramingLine } from "../../components/shared/FramingLine";
import { LoadingSkeleton } from "../../components/shared/LoadingSkeleton";
import { SearchField } from "../../components/shared/SearchField";
import { SectionHeader } from "../../components/shared/SectionHeader";
import { StatTile } from "../../components/shared/StatTile";
import { StudentCard } from "../../components/student/StudentCard";
import { SNAPSHOT_FRAMING, type LearnerSnapshot, toWatchStatus } from "../../lib/presentation";

/**
 * Classroom / Cohort (plan §4.2) — the main working screen. Ordering matters:
 * watched first by priority, then no-current-concern, then Getting Started
 * LAST — never among the no-concern students ("we don't know" and "no
 * concern" are different answers, docs/12 §3). The mock client's
 * getCohort() already returns students in this order; this screen only
 * splits that single ordered list into its two sections without re-sorting.
 */
export default function ClassroomRoute() {
  const { classId } = useParams<{ classId: string }>();
  const [search, setSearch] = useState("");

  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ["cohort", classId],
    queryFn: () => client.getCohort(classId!),
    enabled: !!classId,
  });

  const filtered = useMemo(() => {
    if (!data) return [];
    const query = search.trim().toLowerCase();
    if (query === "") return data.students;
    return data.students.filter((s) => s.displayName.toLowerCase().includes(query));
  }, [data, search]);

  const watching = filtered.filter((s) => toWatchStatus(s).kind === "watching");
  // Preserves the order already returned by the API — no-concern students
  // first, Getting Started last, never interleaved (see doc comment above).
  const allOthers = filtered.filter((s) => toWatchStatus(s).kind !== "watching");

  return (
    <div className="mx-auto flex max-w-[480px] flex-col gap-4 p-4 pb-8">
      <header className="flex items-center justify-between gap-2">
        <Link
          to="/classes"
          aria-label="Back to classes"
          className="flex h-11 min-w-[44px] items-center gap-1 text-sm font-medium text-slate-700"
        >
          ← {isPending ? "" : (data?.className ?? "Class")}
        </Link>
        {/* Class Info dialog is Step 6 — the 44px target exists, inert for now. */}
        <button
          type="button"
          aria-label="Class info"
          className="flex h-11 w-11 items-center justify-center rounded-full border border-slate-300 text-slate-700"
        >
          ⓘ
        </button>
      </header>
      <FramingLine />

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

          {/* The join-requests screen is Step 6 — this banner is inert. */}
          {data.pendingRequestCount > 0 ? (
            <div className="flex min-h-[44px] items-center justify-between rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm text-slate-700">
              <span>
                ⚑ {data.pendingRequestCount} join request
                {data.pendingRequestCount === 1 ? "" : "s"} pending
              </span>
              <span aria-hidden="true">→</span>
            </div>
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
