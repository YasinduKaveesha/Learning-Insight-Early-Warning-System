import { useQuery } from "@tanstack/react-query";
import { client } from "../../api/client";
import { ErrorState } from "../../components/shared/ErrorState";
import { LoadingSkeleton } from "../../components/shared/LoadingSkeleton";

/**
 * Profile (plan §3). The plan specifies nothing beyond the teacher's name
 * and a sign-out affordance — kept deliberately minimal rather than
 * inventing settings, preferences or account management that were never
 * asked for. See the Step 7 report for why sign-out has no handler: there
 * is no auth session in this mock (Step 3 never modelled one), so wiring a
 * destination would be inventing a flow.
 */
export default function ProfileRoute() {
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ["home"],
    queryFn: () => client.getHome(),
  });

  return (
    <div className="mx-auto flex max-w-[480px] flex-col gap-4 p-4 pb-8">
      <h1 className="text-lg font-semibold text-ink-primary">Profile</h1>

      {isPending ? (
        <LoadingSkeleton rows={2} rowHeight={44} />
      ) : isError ? (
        <ErrorState
          message="Couldn't load your profile. Check your connection and try again."
          onRetry={() => refetch()}
        />
      ) : (
        <>
          <p className="text-base text-ink-primary">{data.teacherName}</p>
          <button
            type="button"
            className="mt-4 min-h-[44px] w-full rounded-lg border border-border-strong text-sm font-medium text-ink-primary"
          >
            Sign out
          </button>
        </>
      )}
    </div>
  );
}
