import { ArrowLeft, House } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { client } from "../../api/client";
import { Chart } from "../../components/shared/Chart";
import { DisclosureFooter } from "../../components/shared/DisclosureFooter";
import { ErrorState } from "../../components/shared/ErrorState";
import { FramingLine } from "../../components/shared/FramingLine";
import { ReportsSkeleton } from "../../components/skeletons/PageSkeletons";
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
      {/* Same header as every other screen: a round Back button to the class on
          the left, the title, a round Home button on the right. This page used
          to show a bare "←" character and fell back to /classes, a page that
          no longer exists. */}
      <header className="flex items-center justify-between gap-2">
        {classId ? (
          <Link
            to={`/classes/${classId}`}
            aria-label="Back to class"
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-border-strong text-ink-primary"
          >
            <ArrowLeft aria-hidden="true" size={22} />
          </Link>
        ) : (
          <span className="h-11 w-11 shrink-0" aria-hidden="true" />
        )}
        <h1 className="flex-1 truncate text-center text-base font-semibold text-ink-primary">
          {data ? `${data.className} · Reports` : "Reports"}
        </h1>
        <Link
          to="/"
          aria-label="Home"
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-border-strong text-ink-primary"
        >
          <House aria-hidden="true" size={22} />
        </Link>
      </header>
      <FramingLine />

      {isPending ? (
        <ReportsSkeleton />
      ) : isError ? (
        <ErrorState
          message="Couldn't load reports. Check your connection and try again."
          onRetry={() => refetch()}
        />
      ) : (
        <>
          <section>
            <SectionHeader title="Class learning progress" />
            {data.classLearningProgress.values.length >= 2 ? (
              <Chart
                title="Practice accuracy, class average"
                values={data.classLearningProgress.values}
                trendSentence={describeTrend(
                  "Class average practice accuracy",
                  data.classLearningProgress.values,
                )}
              />
            ) : (
              // The real backend serves no series here: a class-mean accuracy line is
              // QUESTIONS_FOR_ML_TEAM_3 Q4 and has not been ruled on. An empty chart frame
              // reads as "no progress"; this says which it is.
              <NeutralNotice title="Not available yet">
                A class-average progress line is not published yet.
              </NeutralNotice>
            )}
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
            {/* The curve the real backend serves is THIS CLASS, session by session — not the
                study-wide curve the mock supplied. The old title said "across the study",
                which was simply false for the served data. The sentence beneath states the
                scope and nothing about model behaviour: teacher-facing copy about what the
                curve means is QUESTIONS_FOR_ML_TEAM_3 Q6, still unanswered, and we do not
                write that ourselves. */}
            <p className="text-sm text-ink-secondary">
              This class only. Each point counts the learners in it who had a snapshot at that
              session number, so later points may rest on very few learners.
            </p>
            <div className="mt-2">
              <Chart
                title="Share of this class flagged for review, by session"
                values={data.earlyWarningTrend.flagRates}
                trendSentence={describeTrend(
                  "The share of this class flagged",
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
