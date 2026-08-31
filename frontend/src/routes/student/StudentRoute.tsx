import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { client } from "../../api/client";
import { Chart } from "../../components/shared/Chart";
import { DisclosureFooter } from "../../components/shared/DisclosureFooter";
import { ErrorState } from "../../components/shared/ErrorState";
import { FramingLine } from "../../components/shared/FramingLine";
import { LoadingSkeleton } from "../../components/shared/LoadingSkeleton";
import { SectionHeader } from "../../components/shared/SectionHeader";
import { ExplanationBlock } from "../../components/student/ExplanationBlock";
import { RecommendationCard } from "../../components/student/RecommendationCard";
import { SkillProgressList } from "../../components/student/SkillProgress";
import { GettingStartedNotice } from "../../components/status/GettingStartedNotice";
import { PriorityBadge } from "../../components/status/PriorityBadge";
import { TrajectoryChip } from "../../components/status/TrajectoryChip";
import { WatchStatusBadge } from "../../components/status/WatchStatusBadge";
import { describeTrend } from "../../lib/format";
import { SNAPSHOT_FRAMING, type RecommendationDisplay, toWatchStatus } from "../../lib/presentation";

/**
 * Student Overview (plan §4.4). Order matters: status → why → what
 * (skill progress) → evidence (recent activity) → action (suggestions).
 * The Getting Started variant replaces status+why with a single notice;
 * skill progress and recent activity still render — descriptive data is
 * always available, even before there is enough for a watch judgement.
 */
export default function StudentRoute() {
  const { studentId } = useParams<{ studentId: string }>();

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

  // No write-back in v1 (D10) — accept/dismiss/modify only ever update this
  // screen's own local state, seeded from the fetched list. There is no
  // persistence layer for a teacher's decision to land in.
  const [localRecommendations, setLocalRecommendations] = useState<
    RecommendationDisplay[] | null
  >(null);
  const recommendations = localRecommendations ?? recommendationsQuery.data ?? [];

  function updateRecommendation(id: string, patch: Partial<RecommendationDisplay>) {
    setLocalRecommendations(
      recommendations.map((r) => (r.recommendationId === id ? { ...r, ...patch } : r)),
    );
  }

  const isPending = overviewQuery.isPending;
  const isError = overviewQuery.isError;

  return (
    <div className="mx-auto flex max-w-[480px] flex-col gap-4 p-4 pb-8">
      <header className="flex items-center gap-2">
        <Link
          to={overviewQuery.data ? `/classes/${overviewQuery.data.snapshot.classId}` : "/classes"}
          aria-label="Back"
          className="flex h-11 min-w-[44px] items-center text-sm font-medium text-slate-700"
        >
          ←
        </Link>
        <h1 className="text-base font-semibold text-slate-900">
          {isPending ? "" : (overviewQuery.data?.snapshot.displayName ?? "Student")}
        </h1>
      </header>

      <div className="flex gap-4 border-b border-slate-200 text-sm">
        <span className="border-b-2 border-slate-900 pb-2 font-medium text-slate-900">
          Overview
        </span>
        <Link
          to={studentId ? `/students/${studentId}/sessions` : "#"}
          className="pb-2 text-slate-500"
        >
          Sessions
        </Link>
      </div>

      <FramingLine />

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
            <SectionHeader title="Skill progress" />
            <SkillProgressList
              skills={overviewQuery.data.skills}
              bounds={overviewQuery.data.skillBounds}
            />
          </section>

          <section className="flex flex-col gap-4">
            <SectionHeader title="Recent activity" />
            <div>
              <TrajectoryChip trajectory={overviewQuery.data.snapshot.practiceTrajectory} />
              <div className="mt-2">
                <Chart
                  title="Practice accuracy"
                  values={overviewQuery.data.snapshot.accuracySparkline}
                  trendSentence={describeTrend(
                    "Practice accuracy",
                    overviewQuery.data.snapshot.accuracySparkline,
                  )}
                />
              </div>
            </div>
            <div>
              {/* D17: no engagement trajectory chip — the series still
                  renders, with its own descriptive (not classified)
                  trend sentence. */}
              <Chart
                title="Game engagement"
                values={overviewQuery.data.snapshot.engagementSparkline}
                trendSentence={describeTrend(
                  "Game engagement",
                  overviewQuery.data.snapshot.engagementSparkline,
                )}
              />
            </div>
          </section>

          <section>
            <SectionHeader title="Suggestions" />
            {recommendations.length === 0 ? (
              <p className="text-sm text-slate-500">No suggestions right now.</p>
            ) : (
              <div className="flex flex-col gap-3">
                {recommendations.map((r) => (
                  <RecommendationCard
                    key={r.recommendationId}
                    recommendation={r}
                    onAccept={(id) => updateRecommendation(id, { status: "accepted" })}
                    onDismiss={(id) => updateRecommendation(id, { status: "dismissed" })}
                    onModify={(id, modifiedTo) =>
                      updateRecommendation(id, { status: "modified", modifiedActionSummary: modifiedTo })
                    }
                  />
                ))}
              </div>
            )}
          </section>

          <DisclosureFooter disclosure={overviewQuery.data.disclosure} />
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

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-slate-200 bg-white p-4">
      <WatchStatusBadge status={status} />
      {status.kind === "watching" && status.priority !== null ? (
        <PriorityBadge priority={status.priority} context={`in ${className}`} />
      ) : (
        <p className="text-xs text-slate-500">{SNAPSHOT_FRAMING}</p>
      )}
      <ExplanationBlock explanation={snapshot.explanation} />
    </div>
  );
}
