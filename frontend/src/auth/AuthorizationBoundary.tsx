// The one place a 403 is handled (added 2026-10-08).
//
// A VERIFIED SESSION IS NOT AN AUTHORIZED TEACHER -- the backend keeps those
// two steps apart on purpose (401 vs 403), and so must the frontend. RouteGuard
// answers the first question ("is anyone signed in?") and cannot answer the
// second: whether this subject may act as a teacher is only ever learned from
// an API response. So this boundary watches the query and mutation caches, and
// the moment any request comes back 403 it replaces the screen.
//
// WHY APP-LEVEL AND NOT PER-SCREEN. A 403 is a fact about the caller, not about
// the page they happen to be on. Handling it in each route would mean the same
// copy in eight places, every one of them free to drift, and every one of them
// still showing a Try again button that cannot work. Handling it here also
// covers a background prefetch that fails before its screen is ever opened.

import { useEffect, useState, type ReactNode } from "react";
import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { AccountNotAuthorized } from "../components/shared/AccountNotAuthorized";
import { isNotAuthorizedError } from "../lib/apiError";
import { cancelBackgroundLoad } from "../lib/prefetch";
import { useSession } from "./SessionProvider";

/** Has ANY request in this cache already been refused? Read, never stored --
 * the caches are the source of truth and this stays in step with them. */
function hasRefusal(queryClient: QueryClient): boolean {
  return (
    queryClient.getQueryCache().getAll().some((q) => isNotAuthorizedError(q.state.error)) ||
    queryClient.getMutationCache().getAll().some((m) => isNotAuthorizedError(m.state.error))
  );
}

export function AuthorizationBoundary({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { session, signOut } = useSession();
  // Seeded from the cache rather than set in an effect: the failing request may
  // have settled BEFORE this mounted (a prefetch started on the previous
  // screen), in which case no further cache event is coming and a subscription
  // alone would wait forever.
  const [blocked, setBlocked] = useState(() => hasRefusal(queryClient));

  useEffect(() => {
    const onCacheEvent = () => {
      if (hasRefusal(queryClient)) setBlocked(true);
    };
    const unsubscribeQueries = queryClient.getQueryCache().subscribe(onCacheEvent);
    const unsubscribeMutations = queryClient.getMutationCache().subscribe(onCacheEvent);
    return () => {
      unsubscribeQueries();
      unsubscribeMutations();
    };
  }, [queryClient]);

  async function handleSignOut() {
    await signOut();
    cancelBackgroundLoad();
    // The cache must be empty before the next teacher's data can load, and it
    // still holds the refused queries that put us here -- leaving them would
    // block the next sign-in on this tab (frontend_plan 11.0).
    queryClient.clear();
    setBlocked(false);
    navigate("/login", { replace: true });
  }

  if (!blocked) return <>{children}</>;

  return (
    <AccountNotAuthorized
      email={session?.user?.email ?? null}
      onSignOut={() => void handleSignOut()}
    />
  );
}
