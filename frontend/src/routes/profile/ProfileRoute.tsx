import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { client } from "../../api/client";
import { useSession } from "../../auth/SessionProvider";
import { ErrorState } from "../../components/shared/ErrorState";
import { LoadingSkeleton } from "../../components/shared/LoadingSkeleton";

/**
 * Profile (plan §3). The plan specifies nothing beyond the teacher's name
 * and a sign-out affordance — kept deliberately minimal rather than
 * inventing settings, preferences or account management that were never
 * asked for. See the Step 7 report for why sign-out has no handler: there
 * destination would be inventing a flow.
 *
 * B6.3e-1: the session now exists. Sign out clears the Supabase session AND
 * the TanStack Query cache — clearing the cache is not optional, one
 * teacher's cohort must never survive into another teacher's session
 * (frontend_plan §11.0) — then lands on /login.
 */
export default function ProfileRoute() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { signOut } = useSession();

  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ["home"],
    queryFn: () => client.getHome(),
  });

  async function handleSignOut() {
    await signOut();
    // Order matters less than completeness: the cache must be empty before
    // the next teacher's data can load.
    queryClient.clear();
    navigate("/login", { replace: true });
  }

  return (
    <div className="mx-auto flex max-w-[480px] lg:max-w-[1200px] flex-col gap-4 p-4 pb-8">
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
            onClick={() => void handleSignOut()}
            className="mt-4 min-h-[44px] w-full rounded-lg border border-border-strong text-sm font-medium text-ink-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
          >
            Sign out
          </button>
        </>
      )}
    </div>
  );
}
