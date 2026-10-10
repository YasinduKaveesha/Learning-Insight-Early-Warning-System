import { QueryClient } from "@tanstack/react-query";
import { isNotAuthorizedError } from "./apiError";

// Rosters and predictions only change when the pipeline re-runs (plan §8),
// so caching is deliberately generous rather than tuned for freshness.
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      gcTime: 30 * 60 * 1000,
      refetchOnWindowFocus: false,
      // Retry once -- EXCEPT a 403, which is a settled answer about who the
      // caller is, not a blip. Retrying it sends the same token to the same
      // check, doubles the wait before the teacher is told anything, and is
      // invisible to them while it happens.
      retry: (failureCount, error) => !isNotAuthorizedError(error) && failureCount < 1,
    },
  },
});
