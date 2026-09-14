import { useQuery } from "@tanstack/react-query";
import { ArrowRight, House, KeyRound } from "lucide-react";
import { useLayoutEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { client } from "../../api/client";
import { ClassInfoDialog } from "../../components/class/ClassInfoDialog";
import { EmptyState } from "../../components/shared/EmptyState";
import { ErrorState } from "../../components/shared/ErrorState";
import { LoadingSkeleton } from "../../components/shared/LoadingSkeleton";
import { SearchField } from "../../components/shared/SearchField";
import { SectionHeader } from "../../components/shared/SectionHeader";
import { StatTile } from "../../components/shared/StatTile";
import { StudentCard } from "../../components/student/StudentCard";
import {
  isHandledWatch,
  sortCohortOrder,
  type Grade,
  type LearnerSnapshot,
  toWatchStatus,
} from "../../lib/presentation";

// Same grade -> pill colour as the /watch page's class-name pill
// (WatchListScreen.tsx's GRADE_PILL_CLASSES), so the two screens agree.
const GRADE_PILL_CLASSES: Record<Grade, string> = {
  GRADE_2: "bg-watch-watching-fg text-white",
  GRADE_3: "bg-watch-noConcern-fg text-white",
};

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

  // Decision B, 2026-09-14: a flagged learner whose suggestion the teacher has
  // accepted or modified leaves "Students to Watch" and leads "All Students",
  // still in the blue watching tint. The To Watch COUNT does not change.
  const watching = filtered.filter(
    (s) => toWatchStatus(s).kind === "watching" && !isHandledWatch(s),
  );
  const handled = filtered.filter(isHandledWatch);
  // Handled first, then the rest in the order sortCohortOrder produced —
  // no-concern students, then Getting Started last, never interleaved.
  const allOthers = [
    ...handled,
    ...filtered.filter((s) => toWatchStatus(s).kind !== "watching"),
  ];

  // Same scroll layout as Home: the top bar (and the search box, when there is
  // a roster to search) stays pinned; the tiles slide up under it; each section
  // title sticks at its bottom edge, so only the student cards scroll. The
  // pinned block's height is MEASURED -- it changes when the search box appears
  // -- so a title never leaves a gap or hides behind it.
  const pinnedRef = useRef<HTMLDivElement>(null);
  const [pinnedHeight, setPinnedHeight] = useState(0);
  useLayoutEffect(() => {
    const node = pinnedRef.current;
    if (!node) return;
    const measureNode = () => setPinnedHeight(node.getBoundingClientRect().height);
    measureNode();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measureNode);
    observer.observe(node);
    return () => observer.disconnect();
  });

  return (
    <div className="mx-auto flex max-w-[480px] lg:max-w-[1200px] flex-col px-4 pb-8">
      {/* Hardening-pass fix: the back link's aria-label was overriding its
          own visible text, so the class name inside it never reached
          assistive tech at all — a screen-reader user heard only "Back to
          classes" with the class name silently dropped. Split into a
          plain back link plus a real h1 (docs/11 §8: "sane heading
          hierarchy") that actually carries the class name.

          UI-refinement pass: back now goes to Home (not /classes) — /classes
          is no longer reachable from the bottom nav (removed) and Home
          already shows every class, so Home is the actual "back" a teacher
          expects. The Home icon marks that this isn't a plain "go back"
          arrow (per-page convention, see WatchListScreen.tsx). */}
      <div
        ref={pinnedRef}
        className="sticky top-0 z-20 -mx-4 flex flex-col gap-4 bg-background px-4 pb-4 pt-4"
      >
        <header className="flex items-center justify-between gap-2">
          <Link
            to="/"
            aria-label="Home"
            className="flex h-11 w-11 items-center justify-center rounded-full border border-border-strong text-ink-primary"
          >
            <House aria-hidden="true" size={22} />
          </Link>
          <h1 className="flex flex-1 items-center justify-center truncate">
            {/* UI-refinement pass: same coloured pill as the /watch page's
                class-name pill (grade-coloured, solid fill, white text). */}
            {!isPending && data ? (
              <span
                className={`truncate rounded-full px-4 py-1.5 text-base font-semibold ${GRADE_PILL_CLASSES[data.grade]}`}
              >
                {data.className}
              </span>
            ) : null}
          </h1>
          <button
            type="button"
            aria-label="Class info"
            onClick={() => setIsInfoOpen(true)}
            disabled={!data}
            className="flex h-11 w-11 items-center justify-center rounded-full border border-border-strong text-ink-primary disabled:opacity-40"
          >
            <KeyRound aria-hidden="true" size={22} />
          </button>
        </header>
        {data && data.studentCount > 0 ? (
          <SearchField
            label="Search students"
            value={search}
            onChange={setSearch}
            placeholder="Search students..."
            resultCount={filtered.length}
          />
        ) : null}
        {/* The three tiles and the join-requests banner are pinned too, at
            explicit direction (2026-09-14): on this page ONLY the student
            cards scroll. (Home differs on purpose -- its tiles slide under
            the watch card.) */}
        {data ? (
          <>
          {/* UI-refinement pass: same coloured/bold/bottom-right-value style
              as Home's stat tiles (StatTile's `tone` prop). */}
          <div className="grid grid-cols-3 gap-2">
            <StatTile
              label="Students"
              value={data.studentCount}
              tone="blue"
              caption={data.studentCount === 0 ? "Add students" : undefined}
            />
            {/* Already flagged minus handled (D50) -- computed once, in the client. */}
            <StatTile label="To Watch" value={data.toWatchCount} tone="green" />
            <StatTile label="Getting Started" value={data.gettingStartedCount} tone="amber" />
          </div>
            <PendingRequestsBanner classId={classId!} count={data.pendingRequestCount} />
          </>
        ) : null}
      </div>

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
        <div className="flex flex-col gap-4">
          <LoadingSkeleton rows={1} rowHeight={44} />
          <LoadingSkeleton rows={1} rowHeight={72} />
          <LoadingSkeleton rows={4} rowHeight={80} />
        </div>
      ) : isError ? (
        <ErrorState
          message="Couldn't load this class. Check your connection and try again."
          onRetry={() => refetch()}
        />
      ) : (
        <div className="flex flex-col gap-4">
          {/* An empty class is the SAME screen with zeros, not a different
              one. It used to replace everything with a single line, which hid
              the three tiles, hid the class key behind that sentence, and --
              worst -- hid the pending-requests banner, the only route to the
              approve screen. A brand-new class is exactly when the first child
              asks to join: the teacher saw the red dot on Home and had nowhere
              to go. Found on the first real join request, 2026-09-14. */}
          {/* The search box now lives in the pinned block above. */}




          {data.studentCount === 0 ? (
            // The useful empty state is the class key, not "no students" --
            // it is the thing the teacher needs to actually fix this (docs/11
            // section 7's own example: "No learners yet. Share the class key").
            <EmptyState message="No students yet. Share the class key so students can join." />
          ) : null}

          {data.studentCount > 0 ? (
            <>
              <section>
                <div style={{ top: pinnedHeight }} className="sticky z-10 -mx-4 bg-background px-4">
                  <SectionHeader title="Students to Watch" />
                </div>
                {watching.length === 0 ? (
                  <EmptyState message="No students in this class are currently flagged for review." tone="blue" />
                ) : (
                  <StudentCardList students={watching} />
                )}
              </section>

              <section>
                <div style={{ top: pinnedHeight }} className="sticky z-10 -mx-4 bg-background px-4">
                  <SectionHeader title="All Students" />
                </div>
                {allOthers.length === 0 ? (
                  <EmptyState message="No other students to show here." />
                ) : (
                  <StudentCardList students={allOthers} />
                )}
              </section>
            </>
          ) : null}
        </div>
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

/** The teacher's route to the approve/reject screen. Rendered whether or not the
 * class has any students yet — see the empty-state comment above. */
function PendingRequestsBanner({ classId, count }: { classId: string; count: number }) {
  if (count <= 0) return null;
  return (
    // Soft-red tint: an administrative action-needed banner, not a student
    // watch status, so docs/12 §7's "never red for a watch status" does not
    // apply here.
    <Link
      to={`/classes/${classId}/requests`}
      className="flex min-h-[44px] items-center justify-between rounded-lg border border-danger bg-danger-soft px-3 text-sm text-danger-text"
    >
      <span>
        {count} join request{count === 1 ? "" : "s"} pending
      </span>
      <ArrowRight aria-hidden="true" size={20} strokeWidth={3} />
    </Link>
  );
}
