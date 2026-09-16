import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, House } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { client } from "../../api/client";
import { ErrorState } from "../shared/ErrorState";
import { LoadingSkeleton } from "../shared/LoadingSkeleton";
import { SectionHeader } from "../shared/SectionHeader";
import { RecommendationCard } from "./RecommendationCard";
import { SkillProgressList } from "./SkillProgress";
import { GettingStartedNotice } from "../status/GettingStartedNotice";
import { PriorityBadge } from "../status/PriorityBadge";
import {
  isRecommendationConflictError,
  recommendationDecisionError,
  snapshotFraming,
  type RecommendationDisplay,
  toWatchStatus,
} from "../../lib/presentation";

export interface StudentDetailProps {
  studentId: string | undefined;
  /** Where the sessions tab link points. Only the standalone route (not the
   * ≥1024 master-detail pane) needs the tab bar — the pane doesn't have its
   * own sub-route for session history, so it's omitted there. */
  showSessionsTab?: boolean;
}

/**
 * Student Overview (plan §4.4). Order matters: status → why → what
 * (skill progress) → evidence (recent activity) → action (suggestions).
 * The Getting Started variant replaces status+why with a single notice;
 * skill progress and recent activity still render — descriptive data is
 * always available, even before there is enough for a watch judgement.
 *
 * Shared between the standalone `/students/:studentId` route and the
 * ≥1024px watch-list master-detail pane (hardening-pass gap 2) — this is
 * the one place the screen is rendered; neither caller duplicates it.
 */
export function StudentDetail({ studentId, showSessionsTab = true }: StudentDetailProps) {
  const overviewQuery = useQuery({
    queryKey: ["studentOverview", studentId],
    queryFn: () => client.getStudentOverview(studentId!),
    enabled: !!studentId,
  });

  const recommendationsQuery = useQuery({
    queryKey: ["studentRecommendations", studentId],
    queryFn: () => client.getStudentRecommendations(studentId!),
    enabled: !!studentId,
  });

  // Decisions are SAVED to Component 3's decision log (docs/13 §6 — the log
  // is a research output). Saving never changes what Component B or C does
  // (D10). The returned suggestion replaces the one on screen, so what the
  // teacher sees is what the server stored, not what the click assumed.
  const queryClient = useQueryClient();
  const [savedRecommendations, setSavedRecommendations] = useState<
    Record<string, RecommendationDisplay>
  >({});
  const [savingId, setSavingId] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const recommendations = (recommendationsQuery.data ?? []).map(
    (r) => savedRecommendations[r.recommendationId] ?? r,
  );

  async function decide(id: string, save: () => Promise<RecommendationDisplay>) {
    setSavingId(id);
    setErrors(({ [id]: _dropped, ...rest }) => rest);
    try {
      const saved = await save();
      setSavedRecommendations((prev) => ({ ...prev, [id]: saved }));
      // Decision B: an accepted or modified suggestion moves this learner on
      // the class page and adds to its "handled" caption. Refresh those lists
      // now, so going back shows the move without a manual reload.
      void queryClient.invalidateQueries({ queryKey: ["cohort"] });
      void queryClient.invalidateQueries({ queryKey: ["home"] });
      void queryClient.invalidateQueries({ queryKey: ["watch"] });
      void queryClient.invalidateQueries({ queryKey: ["classWatch"] });
      // This learner's suggestions may have been seeded from a class-wide read
      // before the decision; refetch them so revisiting shows the saved state,
      // not stale Accept/Modify buttons. The class read is refetched too.
      void queryClient.invalidateQueries({ queryKey: ["studentRecommendations", studentId] });
      void queryClient.invalidateQueries({ queryKey: ["classStudentOverviews"] });
    } catch (e) {
      setErrors((prev) => ({ ...prev, [id]: recommendationDecisionError(e) }));
      // Already decided or expired elsewhere (another tab, another device):
      // re-read so the card shows the stored state rather than stale buttons.
      if (isRecommendationConflictError(e)) void recommendationsQuery.refetch();
    } finally {
      setSavingId(null);
    }
  }

  const isPending = overviewQuery.isPending;
  const isError = overviewQuery.isError;

  return (
    <div className="mx-auto flex max-w-[480px] lg:max-w-[1200px] flex-col gap-4 p-4 pb-8">
      {/* PINNED: the header and the Overview/Sessions tabs stay at the top; only
          the content below scrolls (explicit direction, 2026-09-14). -mx-4 and
          -mt-4 stretch its page-coloured background over the column padding,
          so content scrolling up disappears beneath it cleanly. */}
      <div className="sticky top-0 z-20 -mx-4 -mt-4 flex flex-col gap-4 bg-background px-4 pb-2 pt-4">
        <header className="flex items-center justify-between gap-2">
          {/* Back goes to this student's class. Until the class is known (still
              loading, or a learner with no class) it goes Home and SAYS so with
              the Home icon -- an arrow must never point somewhere that is not
              actually back. It used to fall back to /classes, a page that no
              longer exists. */}
          {overviewQuery.data?.snapshot.classId ? (
            <Link
              to={`/classes/${overviewQuery.data.snapshot.classId}`}
              aria-label="Back to class"
              className="flex h-11 w-11 items-center justify-center rounded-full border border-border-strong text-ink-primary"
            >
              <ArrowLeft aria-hidden="true" size={22} />
            </Link>
          ) : (
            <Link
              to="/"
              aria-label="Home"
              className="flex h-11 w-11 items-center justify-center rounded-full border border-border-strong text-ink-primary"
            >
              <House aria-hidden="true" size={22} />
            </Link>
          )}
          <h1 className="flex-1 truncate text-center text-[18px] font-bold text-ink-primary">
            {isPending ? "" : (overviewQuery.data?.snapshot.displayName ?? "Student")}
          </h1>
          <Link
            to="/"
            aria-label="Home"
            className="flex h-11 w-11 items-center justify-center rounded-full border border-border-strong text-ink-primary"
          >
            <House aria-hidden="true" size={22} />
          </Link>
        </header>

        {showSessionsTab ? (
          // Hardening-pass fix: these tabs were sized to their text
          // (pb-2 only), well under the 44px touch-target minimum — fixed
          // with a flex+min-h wrapper on each tab rather than changing what
          // they say or do.
          // UI-refinement pass: pill-shaped, coloured, centered — replacing
          // the underline-tab look.
          <div className="flex justify-center gap-3">
            <span className="flex min-h-[44px] items-center justify-center rounded-full bg-watch-watching-bg px-5 text-base font-bold text-watch-watching-fg">
              Overview
            </span>
            <Link
              to={studentId ? `/students/${studentId}/sessions` : "#"}
              className="flex min-h-[44px] items-center justify-center rounded-full bg-surface2 px-5 text-base font-bold text-ink-secondary"
            >
              Sessions
            </Link>
          </div>
        ) : null}
      </div>

      {isPending ? (
        <>
          <LoadingSkeleton rows={1} rowHeight={100} />
          <LoadingSkeleton rows={1} rowHeight={160} />
          <LoadingSkeleton rows={1} rowHeight={160} />
        </>
      ) : isError ? (
        <ErrorState
          message="Couldn't load this student. Check your connection and try again."
          onRetry={() => overviewQuery.refetch()}
        />
      ) : (
        <>
          <StatusAndWhy
            snapshot={overviewQuery.data.snapshot}
            className={overviewQuery.data.className}
          />

          <section>
            <SectionHeader title="Skill progress" boldTitle />
            <SkillProgressList
              skills={overviewQuery.data.skills}
              bounds={overviewQuery.data.skillBounds}
            />
          </section>

          <section>
            <SectionHeader title="Suggestions" boldTitle />
            {recommendations.length === 0 ? (
              <p className="text-sm text-ink-secondary">No suggestions right now.</p>
            ) : (
              <div className="flex flex-col gap-3">
                {recommendations.map((r) => (
                  <RecommendationCard
                    key={r.recommendationId}
                    recommendation={r}
                    isSaving={savingId === r.recommendationId}
                    errorMessage={errors[r.recommendationId] ?? null}
                    onAccept={(id) => decide(id, () => client.acceptRecommendation(id))}
                    onModify={(id, action) =>
                      decide(id, () => client.modifyRecommendation(id, action))
                    }
                  />
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}

function StatusAndWhy({
  snapshot,
  className,
}: {
  snapshot: Parameters<typeof toWatchStatus>[0];
  className: string;
}) {
  const status = toWatchStatus(snapshot);

  if (status.kind === "getting_started") {
    return (
      <GettingStartedNotice
        name={snapshot.displayName}
        sessionsCompleted={status.sessionsCompleted}
        sessionsRequired={status.sessionsRequired}
      />
    );
  }

  // UI-refinement pass: for a no-concern student this card was just the
  // "Based on recent learning activity" framing line on its own (no
  // priority, usually no explanation either) — removed entirely at
  // explicit direction rather than rendering an empty-feeling card.
  if (status.kind === "no_concern") {
    return null;
  }

  // The explanation paragraph ("Flagged for teacher review. Signals
  // contributing to this include ...") was removed from this card at explicit
  // direction, 2026-09-14. The card now carries only the scope line.
  //
  // UI-refinement pass: the "Worth watching right now" status badge is
  // removed — the card's own green tint (watch.noConcern) carries the
  // status instead. Note: watch.noConcern is normally "no current
  // concern," reused here purely as a colour, not as a status re-label —
  // this card is still for a watching/flagged student.
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-watch-noConcern-border bg-watch-noConcern-bg p-4">
      {status.kind === "watching" && status.priority !== null ? (
        <PriorityBadge priority={status.priority} context={`in ${className}`} />
      ) : (
        // Personalised from this learner's own figures (see snapshotFraming).
        // With D39's priority withdrawn, the generic line was the only thing
        // left in this slot and said nothing specific to the child.
        <p className="text-sm text-ink-secondary">
          {snapshotFraming(snapshot.sessionsCompleted, className)}
        </p>
      )}
    </div>
  );
}
