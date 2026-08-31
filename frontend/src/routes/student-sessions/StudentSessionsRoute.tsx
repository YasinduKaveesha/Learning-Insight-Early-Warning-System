import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { client } from "../../api/client";
import { DisclosureFooter } from "../../components/shared/DisclosureFooter";
import { EmptyState } from "../../components/shared/EmptyState";
import { ErrorState } from "../../components/shared/ErrorState";
import { FramingLine } from "../../components/shared/FramingLine";
import { LoadingSkeleton } from "../../components/shared/LoadingSkeleton";
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
    <div className="mx-auto flex max-w-[480px] flex-col gap-4 p-4 pb-8">
      <header className="flex items-center gap-2">
        <Link
          to={studentId ? `/students/${studentId}` : "/classes"}
          aria-label="Back"
          className="flex h-11 min-w-[44px] items-center text-sm font-medium text-ink-primary"
        >
          ←
        </Link>
        <h1 className="text-base font-semibold text-ink-primary">
          {overviewQuery.data?.snapshot.displayName ?? "Student"}
        </h1>
      </header>

      <div className="flex gap-4 border-b border-border text-sm">
        <Link
          to={studentId ? `/students/${studentId}` : "/classes"}
          className="pb-2 text-ink-secondary"
        >
          Overview
        </Link>
        <span className="border-b-2 border-foreground pb-2 font-medium text-ink-primary">
          Sessions
        </span>
      </div>

      <FramingLine />

      {isPending ? (
        <LoadingSkeleton rows={3} rowHeight={140} />
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
        <>
          <div className="flex flex-col gap-3">
            {sessionsQuery.data!.map((session) => (
              <SessionCard key={session.sessionNumber} session={session} />
            ))}
          </div>
          <DisclosureFooter disclosure={overviewQuery.data!.disclosure} />
        </>
      )}
    </div>
  );
}
