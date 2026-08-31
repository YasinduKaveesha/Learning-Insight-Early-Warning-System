import { QueryClient } from "@tanstack/react-query";

// Rosters and predictions only change when the pipeline re-runs (plan §8),
// so caching is deliberately generous rather than tuned for freshness.
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      gcTime: 30 * 60 * 1000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});
