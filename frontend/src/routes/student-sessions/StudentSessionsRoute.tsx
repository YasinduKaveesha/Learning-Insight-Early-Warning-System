import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, House } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { client } from "../../api/client";
import { EmptyState } from "../../components/shared/EmptyState";
import { ErrorState } from "../../components/shared/ErrorState";
import { StudentSessionsSkeleton } from "../../components/skeletons/PageSkeletons";
import { SessionCard } from "../../components/student/SessionCard";

/**
 * Session History (plan §4.5). One card per session, headed "Session N" and
 * the date — SessionCard (Step 4) already carries the three docs/03 §7
 * rules (B/C never merged, an absent component reads as a gap, a technical
 * fault never reads as disengagement). This route's only job is fetching
 * the list and handing it, in order, to that component — no renumbering,
 * no re-deriving a composite.
 */
export default function StudentSessionsRoute() {
  const { studentId } = useParams<{ studentId: string }>();

  // getStudentOverview supplies the name, class link and disclosure this
  // screen needs; getStudentSessions supplies the session list. There is no
  // single envelope carrying both (Step 3's getStudentSessions returns a
  // bare array), so both are fetched in parallel rather than widening that
  // endpoint's contract for a header this is the only screen to need.
  const overviewQuery = useQuery({
    queryKey: ["studentOverview", studentId],
    queryFn: () => client.getStudentOverview(studentId!),
    enabled: !!studentId,
  });
  const sessionsQuery = useQuery({
    queryKey: ["studentSessions", studentId],
    queryFn: () => client.getStudentSessions(studentId!),
    enabled: !!studentId,
  });

  const isPending = overviewQuery.isPending || sessionsQuery.isPending;
  const isError = overviewQuery.isError || sessionsQuery.isError;

  return (
    <div className="mx-auto flex max-w-[480px] lg:max-w-[1200px] flex-col gap-4 p-4 pb-8">
      {/* PINNED, matching the Overview page: header and tabs stay at the top,
          only the session cards scroll (explicit direction, 2026-09-14). */}
      <div className="sticky top-0 z-20 -mx-4 -mt-4 flex flex-col gap-4 bg-background px-4 pb-2 pt-4">
        <header className="flex items-center justify-between gap-2">
          <Link
            to={studentId ? `/students/${studentId}` : "/"}
            aria-label="Back"
            className="flex h-11 w-11 items-center justify-center rounded-full border border-border-strong text-ink-primary"
          >
            <ArrowLeft aria-hidden="true" size={22} />
          </Link>
          <h1 className="flex-1 truncate text-center text-[18px] font-bold text-ink-primary">
            {overviewQuery.data?.snapshot.displayName ?? "Student"}
          </h1>
          <Link
            to="/"
            aria-label="Home"
            className="flex h-11 w-11 items-center justify-center rounded-full border border-border-strong text-ink-primary"
          >
            <House aria-hidden="true" size={22} />
          </Link>
        </header>

        {/* Hardening-pass fix: matches StudentDetail's tab-bar fix — was
            sized to text only (pb-2), under the 44px touch-target minimum.
            UI-refinement pass: pill-shaped, coloured, centered — matching
            StudentDetail's Overview/Sessions tabs. */}
        <div className="flex justify-center gap-3">
          <Link
            to={studentId ? `/students/${studentId}` : "/"}
            className="flex min-h-[44px] items-center justify-center rounded-full bg-surface2 px-5 text-base font-bold text-ink-secondary"
          >
            Overview
          </Link>
          <span className="flex min-h-[44px] items-center justify-center rounded-full bg-watch-watching-bg px-5 text-base font-bold text-watch-watching-fg">
            Sessions
          </span>
        </div>
      </div>

      {isPending ? (
        <StudentSessionsSkeleton />
      ) : isError ? (
        <ErrorState
          message="Couldn't load session history. Check your connection and try again."
          onRetry={() => {
            void overviewQuery.refetch();
            void sessionsQuery.refetch();
          }}
        />
      ) : sessionsQuery.data!.length === 0 ? (
        <EmptyState message="No sessions recorded yet." />
      ) : (
        <div className="flex flex-col gap-3">
          {sessionsQuery.data!.map((session) => (
            <SessionCard key={session.sessionNumber} session={session} />
          ))}
        </div>
      )}
    </div>
  );
}
