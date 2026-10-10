import { useIsFetching, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { classIdFromPath } from "../../lib/classPath";
import {
  ensureWarmUp,
  pauseBackgroundLoad,
  prioritiseClass,
  resumeBackgroundLoad,
} from "../../lib/prefetch";

/** How long the app must be idle before the warm-up is let back in. Long
 * enough that a screen whose second query starts just after its first one
 * finishes is treated as still loading, short enough to be imperceptible. */
const IDLE_MS = 60;


/**
 * THE SCREEN THE TEACHER IS ON LOADS FIRST. ALWAYS.
 *
 * Renders nothing. It states one rule for every route, rather than leaving
 * each screen to defend itself:
 *
 *   1. Any navigation -- a link, the back button, or a reload on a deep link
 *      -- holds the background warm-up immediately.
 *   2. The warm-up is let back in once nothing is fetching, i.e. once the
 *      screen has what it needs.
 *   3. If no plan exists yet, one is made at that first idle moment. A teacher
 *      who reloads on /classes/:id/requests never mounts Home, and before this
 *      that meant no warm-up ever ran for the rest of the session.
 *
 * `useIsFetching` counts the open screen's queries and the one background task
 * that may still be in flight (a request cannot be un-sent). Both must finish
 * before the queue resumes, which is exactly the intent: nothing competes with
 * the page being looked at.
 *
 * Class screens additionally call `focusClass`, which loads that class's own
 * page, watch list and learners ahead of everything else. This component
 * decides WHEN the background may run; `focusClass` decides WHAT runs first
 * when it does.
 */
export function ForegroundPriority() {
  const location = useLocation();
  const queryClient = useQueryClient();
  const fetching = useIsFetching();

  // Hold the moment the route changes -- before the new screen's queries are
  // even started, so the warm-up cannot get a request in ahead of them.
  useEffect(() => {
    pauseBackgroundLoad();
  }, [location.pathname]);

  useEffect(() => {
    if (fetching > 0) return;
    // Idle. Wait a beat before resuming: a screen that fetches in two steps
    // (a list, then its detail) is momentarily at zero between them, and
    // resuming there would put background work between the two.
    const timer = setTimeout(() => {
      void ensureWarmUp(queryClient);
      // Whatever class this screen is about goes to the front of the queue --
      // including its /requests and /reports screens, which ClassroomRoute's
      // own `focusClass` never covered. Pure re-ordering, no extra request, so
      // it costs a teacher on one of those screens nothing.
      const classId = classIdFromPath(location.pathname);
      if (classId) prioritiseClass(classId);
      resumeBackgroundLoad();
    }, IDLE_MS);
    return () => clearTimeout(timer);
  }, [fetching, location.pathname, queryClient]);

  return null;
}
