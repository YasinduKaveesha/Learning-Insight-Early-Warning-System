import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { client } from "../../api/client";
import { Chart } from "../../components/shared/Chart";
import { DisclosureFooter } from "../../components/shared/DisclosureFooter";
import { ErrorState } from "../../components/shared/ErrorState";
import { FramingLine } from "../../components/shared/FramingLine";
import { LoadingSkeleton } from "../../components/shared/LoadingSkeleton";
import { NeutralNotice } from "../../components/shared/NeutralNotice";
import { SectionHeader } from "../../components/shared/SectionHeader";
import { StatTile } from "../../components/shared/StatTile";
import { describeTrend } from "../../lib/format";

/**
 * Reports (plan §4.6). Four sections: class learning progress · students to
 * watch over time · early-warning trend · participation.
 *
 * NEVER SHOWN HERE, and this is the whole risk of this screen: precision,
 * recall, F1, AUC, lift, calibration, a confusion matrix, or any breakdown
 * by research cohort group. Those are evidence for what the product may
 * do, not content for a teacher — this screen is the most likely place in
 * the app for a research metric to leak in, because the underlying data
 * sits right there in the fixtures. Nothing in ClassReportsResponse (see
 * api/client.ts) carries one; a source-and-render scan test asserts it.
 */
export default function ClassroomReportsRoute() {
  const { classId } = useParams<{ classId: string }>();

  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ["classReports", classId],
    queryFn: () => client.getClassReports(classId!),
    enabled: !!classId,
  });

  return (
    <div className="mx-auto flex max-w-[480px] lg:max-w-[1200px] flex-col gap-4 p-4 pb-8">
      <header className="flex items-center gap-2">
        <Link
          to={classId ? `/classes/${classId}` : "/classes"}
          aria-label="Back to class"
          className="flex h-11 min-w-[44px] items-center text-sm font-medium text-ink-primary"
        >
          ←
        </Link>
        <h1 className="text-base font-semibold text-ink-primary">
          {data ? `${data.className} · Reports` : "Reports"}
        </h1>
      </header>
      <FramingLine />

      {isPending ? (
        <>
          <LoadingSkeleton rows={1} rowHeight={120} />
          <LoadingSkeleton rows={1} rowHeight={120} />
          <LoadingSkeleton rows={1} rowHeight={120} />
          <LoadingSkeleton rows={1} rowHeight={80} />
        </>
      ) : isError ? (
        <ErrorState
          message="Couldn't load reports. Check your connection and try again."
          onRetry={() => refetch()}
        />
      ) : (
        <>
          <section>
            <SectionHeader title="Class learning progress" />
            <Chart
              title="Practice accuracy, class average"
              values={data.classLearningProgress.values}
              trendSentence={describeTrend(
                "Class average practice accuracy",
                data.classLearningProgress.values,
              )}
            />
          </section>

          <section>
            <SectionHeader title="Students to watch over time" />
            {/* Step 8 fix: this used to be a chart scaled from the SAME
                series the Early-warning trend section renders directly
                below — two charts agreeing because they were one curve,
                which manufactures apparent evidence (docs/12 §7). There is
                no real per-class longitudinal watch-count in any artefact,
                so this renders an honest absence instead of a guess. */}
            <NeutralNotice title="Not enough history yet">
              This class has one snapshot of watch data; this section will fill in as more
              sessions are completed.
            </NeutralNotice>
          </section>

          <section>
            <SectionHeader title="Early-warning trend" />
            <p className="text-sm text-ink-secondary">{data.earlyWarningTrend.explanation}</p>
            <div className="mt-2">
              <Chart
                title="Share of students flagged, across the study"
                values={data.earlyWarningTrend.flagRates}
                trendSentence={describeTrend(
                  "The share of students flagged",
                  data.earlyWarningTrend.flagRates,
                )}
              />
            </div>
          </section>

          <section>
            <SectionHeader title="Participation" />
            <div className="grid grid-cols-3 gap-2">
              {data.participation.map((bucket) => (
                <StatTile
                  key={bucket.bucketLabel}
                  label={bucket.bucketLabel}
                  value={bucket.studentCount}
                />
              ))}
            </div>
          </section>

          <DisclosureFooter disclosure={data.disclosure} />
        </>
      )}
    </div>
  );
}
