import { ArrowLeft, House } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { client } from "../../api/client";
import { EmptyState } from "../../components/shared/EmptyState";
import { ErrorState } from "../../components/shared/ErrorState";
import { JoinRequestsSkeleton } from "../../components/skeletons/PageSkeletons";
import { formatDate } from "../../lib/format";
import type { PendingRequestDisplay } from "../../lib/presentation";

/**
 * Join requests (plan §4.7, docs/11 §4). Pending requests sit ABOVE the
 * roster because they are the thing requiring action — this screen shows
 * only the requests, reached from the Cohort screen's banner, which is the
 * roster context. Empty state shows the class key again so the teacher can
 * re-share it — that's the useful empty state, not "no requests".
 */
export default function ClassroomRequestsRoute() {
  const { classId } = useParams<{ classId: string }>();
  const queryClient = useQueryClient();

  const cohortQuery = useQuery({
    queryKey: ["cohort", classId],
    queryFn: () => client.getCohort(classId!),
    enabled: !!classId,
  });

  const requestsQuery = useQuery({
    queryKey: ["joinRequests", classId],
    queryFn: () => client.getJoinRequests(classId!),
    enabled: !!classId,
  });

  const isPending = cohortQuery.isPending || requestsQuery.isPending;
  const isError = cohortQuery.isError || requestsQuery.isError;

  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: ["joinRequests", classId] });
    void queryClient.invalidateQueries({ queryKey: ["cohort", classId] });
  }

  async function handleApprove(requestId: string) {
    await client.approveJoinRequest(classId!, requestId);
    invalidate();
  }

  async function handleReject(requestId: string) {
    await client.rejectJoinRequest(classId!, requestId);
    invalidate();
  }

  return (
    <div className="mx-auto flex max-w-[480px] lg:max-w-[1200px] flex-col gap-4 p-4 pb-8">
      {/* Same header as every other screen: a round Back button to the class on
          the left, the title, a round Home button on the right. This page used
          to show a bare "←" character and fell back to /classes, a page that
          no longer exists. */}
      <header className="flex items-center justify-between gap-2">
        {classId ? (
          <Link
            to={`/classes/${classId}`}
            aria-label="Back to class"
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-border-strong text-ink-primary"
          >
            <ArrowLeft aria-hidden="true" size={22} />
          </Link>
        ) : (
          <span className="h-11 w-11 shrink-0" aria-hidden="true" />
        )}
        <h1 className="flex-1 truncate text-center text-base font-semibold text-ink-primary">
          Join Requests
        </h1>
        <Link
          to="/"
          aria-label="Home"
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-border-strong text-ink-primary"
        >
          <House aria-hidden="true" size={22} />
        </Link>
      </header>

      {isPending ? (
        <JoinRequestsSkeleton />
      ) : isError ? (
        <ErrorState
          message="Couldn't load join requests. Check your connection and try again."
          onRetry={() => {
            void cohortQuery.refetch();
            void requestsQuery.refetch();
          }}
        />
      ) : (
        <>
          {requestsQuery.data!.length === 0 ? (
            <EmptyState
              message="No requests pending right now. Share the class key so students can join."
            />
          ) : (
            <div className="flex flex-col gap-3">
              {requestsQuery.data!.map((r) => (
                <RequestCard key={r.requestId} request={r} onApprove={handleApprove} onReject={handleReject} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function RequestCard({
  request,
  onApprove,
  onReject,
}: {
  request: PendingRequestDisplay;
  onApprove: (requestId: string) => void;
  onReject: (requestId: string) => void;
}) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border bg-surface1 p-4">
      <div>
        <p className="text-sm font-semibold text-ink-primary">{request.studentDisplayName}</p>
        <p className="text-sm text-ink-secondary">Requested {formatDate(request.requestedDate)}</p>
      </div>

      {/* Approve / Reject: ≥44px, NEVER ADJACENT, distinguished by label —
          same visual-separation ruling as RecommendationCard's Accept /
          Modify (Step 5 review ruling A): a solid full-width Approve, then
          real vertical distance and a rule before an outline Reject, not a
          spacer between two identical buttons. Colours follow the app's own
          buttons (the navy "View watch list" pill), 2026-09-14. */}
      <div className="flex flex-col gap-3 pt-1">
        <button
          type="button"
          onClick={() => onApprove(request.requestId)}
          className="min-h-[44px] w-full rounded-full bg-watch-watching-fg px-3 text-sm font-bold text-white"
        >
          Approve
        </button>
        <div className="border-t border-border pt-3">
          <button
            type="button"
            onClick={() => onReject(request.requestId)}
            className="min-h-[44px] w-full rounded-full border-2 border-border-strong bg-surface1 px-3 text-sm font-semibold text-ink-primary"
          >
            Reject
          </button>
        </div>
      </div>
    </div>
  );
}
