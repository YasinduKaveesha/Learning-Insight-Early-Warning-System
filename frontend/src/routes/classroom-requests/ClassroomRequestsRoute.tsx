import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { client } from "../../api/client";
import { DisclosureFooter } from "../../components/shared/DisclosureFooter";
import { EmptyState } from "../../components/shared/EmptyState";
import { ErrorState } from "../../components/shared/ErrorState";
import { FramingLine } from "../../components/shared/FramingLine";
import { LoadingSkeleton } from "../../components/shared/LoadingSkeleton";
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
    <div className="mx-auto flex max-w-[480px] flex-col gap-4 p-4 pb-8">
      <header className="flex items-center gap-2">
        <Link
          to={classId ? `/classes/${classId}` : "/classes"}
          aria-label="Back to class"
          className="flex h-11 min-w-[44px] items-center text-sm font-medium text-slate-700"
        >
          ←
        </Link>
        <h1 className="text-base font-semibold text-slate-900">Join Requests</h1>
      </header>
      <FramingLine />

      {isPending ? (
        <LoadingSkeleton rows={2} rowHeight={96} />
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
              message={`No requests pending right now. Share the key ${cohortQuery.data!.classKey} so students can join.`}
            />
          ) : (
            <div className="flex flex-col gap-3">
              {requestsQuery.data!.map((r) => (
                <RequestCard key={r.requestId} request={r} onApprove={handleApprove} onReject={handleReject} />
              ))}
            </div>
          )}

          <DisclosureFooter disclosure={cohortQuery.data!.disclosure} />
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
    <div className="flex flex-col gap-2 rounded-lg border border-slate-200 bg-white p-4">
      <div>
        <p className="text-sm font-semibold text-slate-900">{request.studentDisplayName}</p>
        <p className="text-xs text-slate-500">Requested {formatDate(request.requestedDate)}</p>
      </div>

      {/* Approve / Reject: ≥44px, NEVER ADJACENT, distinguished by label —
          same visual-separation ruling as RecommendationCard's Accept /
          Modify / Dismiss (Step 5 review ruling A): a solid full-width
          Approve, then real vertical distance and a rule before an
          understated Reject, not a spacer between two identical buttons. */}
      <div className="flex flex-col gap-3 pt-1">
        <button
          type="button"
          onClick={() => onApprove(request.requestId)}
          className="min-h-[44px] w-full rounded-lg bg-slate-900 px-3 text-sm font-semibold text-white"
        >
          Approve
        </button>
        <div className="border-t border-slate-200 pt-3">
          <button
            type="button"
            onClick={() => onReject(request.requestId)}
            className="min-h-[44px] w-full rounded-lg px-3 text-sm font-medium text-slate-600 underline underline-offset-2"
          >
            Reject
          </button>
        </div>
      </div>
    </div>
  );
}
