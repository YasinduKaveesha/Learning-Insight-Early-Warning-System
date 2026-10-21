import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { useLocation, useParams } from "react-router-dom";
import { compd, compdRetry, type CompdProfile } from "../../api/compdClient";
import { EmptyState } from "../../components/shared/EmptyState";
import { ErrorState } from "../../components/shared/ErrorState";
import {
  DIMENSIONS,
  LEGEND,
  TONE_CHIP_CLASSES,
  basedOn,
  classLine,
  dateAndTime,
  loadErrorMessage,
  pct,
  profilesRecorded,
  seconds,
  studentName,
} from "../../lib/compdPresentation";
import { CompdPageSkeleton } from "./CompdPageSkeleton";
import { CompdHeader, LevelBar, LevelChip } from "./CompdParts";

/** compD's history call asked for its default page of profiles. */
const HISTORY_LIMIT = 20;

/**
 * /compd/students/:studentId -- compD's teacher view of one child: the Profile
 * (ProfileResultScreen.tsx, teacher view) on top and the History
 * (ProfileHistoryScreen.tsx) below, from ONE call whose first item is the latest.
 *
 * Not shown, by decision: a confidence value, the model version, and compD's
 * brain-power circle, badge and personal-best ribbon (Q14) -- none of them reach
 * this page. Nor the child-facing level messages; the blurbs and bars stay.
 */
export default function CompdStudentRoute() {
  const { studentId = "" } = useParams<{ studentId: string }>();
  const location = useLocation();
  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ["compd", "student", studentId],
    queryFn: () => compd.getStudentProfiles(studentId, HISTORY_LIMIT),
    retry: compdRetry,
  });

  // React Router does not scroll to a hash, and the skeleton renders first, so
  // "History" from a student card lands here at the top. Once the data is in,
  // bring the section into view. Guarded like SelectField's: jsdom and older
  // browsers have no scrollIntoView, and a missing scroll must never break the page.
  useEffect(() => {
    if (!data || location.hash !== "#history") return;
    const section = document.getElementById("history");
    if (section && typeof section.scrollIntoView === "function") {
      section.scrollIntoView({ block: "start" });
    }
  }, [data, location.hash]);

  const latest = data?.items[0];

  return (
    <div className="mx-auto flex max-w-[480px] lg:max-w-[1200px] flex-col gap-4 p-4 pb-8">
      <CompdHeader
        title={data ? studentName(data.name) : "Student"}
        backTo="/compd?tab=students"
        backLabel="Back to Thinking Skills"
      />

      {isPending ? (
        <CompdPageSkeleton variant="profile" label="Loading profile" />
      ) : isError ? (
        <ErrorState message={loadErrorMessage(error)} onRetry={() => refetch()} />
      ) : (
        <>
          {/* Added, not compD: which class the child is in. */}
          <p className="-mt-2 text-center text-sm text-ink-secondary">
            {classLine(data.classroom_name, null)}
          </p>

          {latest ? (
            <ProfileSection profile={latest} />
          ) : (
            <EmptyState message="This student hasn't done a Thinking Skills activity yet." />
          )}

          {data.items.length > 0 ? <HistorySection items={data.items} /> : null}
        </>
      )}
    </div>
  );
}

function ProfileSection({ profile }: { profile: CompdProfile }) {
  const f = profile.features;
  return (
    <section aria-labelledby="profile-heading" className="flex flex-col gap-3">
      <div className="flex flex-col items-center gap-1 rounded-lg border border-border bg-surface1 p-4 text-center">
        <h2 id="profile-heading" className="text-lg font-bold text-ink-primary">
          Cognitive Skill Profile
        </h2>
        <p className="text-sm text-ink-secondary">{basedOn(f.total_questions, f.accuracy)}</p>
      </div>

      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {DIMENSIONS.map((d) => (
          <li key={d.key} className="flex flex-col gap-2 rounded-lg border border-border bg-surface1 p-4">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-base font-bold text-ink-primary">{d.title}</h3>
              <LevelChip level={profile[d.key]} />
            </div>
            <p className="text-sm text-ink-secondary">{d.blurb}</p>
            <LevelBar level={profile[d.key]} />
          </li>
        ))}
      </ul>

      <div className="flex flex-col gap-1 rounded-lg border border-watch-watching-border bg-watch-watching-bg p-4">
        <h3 className="text-base font-bold text-watch-watching-fg">Suggested focus</h3>
        <p className="whitespace-pre-line text-sm text-watch-watching-fg">{profile.recommendation}</p>
      </div>

      {/* compD's "Detailed Stats", in the units the student card uses: seconds
          and percentages (compD showed milliseconds and a decimal hint rate). */}
      <dl className="grid grid-cols-2 gap-2 rounded-lg border border-border bg-surface1 p-4 sm:grid-cols-4">
        <Stat label="Avg time" value={seconds(f.avg_response_time_ms / 1000)} />
        <Stat label="Retry rate" value={pct(f.retry_rate)} />
        <Stat label="Hint rate" value={pct(f.hint_rate)} />
        <Stat label="Interactions" value={String(f.total_questions)} />
      </dl>
    </section>
  );
}

function HistorySection({ items }: { items: CompdProfile[] }) {
  return (
    <section id="history" aria-labelledby="history-heading" className="flex scroll-mt-28 flex-col gap-3">
      <div className="px-1">
        <h2 id="history-heading" className="text-lg font-bold text-ink-primary">
          Profile History
        </h2>
        <p className="text-sm text-ink-secondary">{profilesRecorded(items.length)}</p>
      </div>

      <ol className="flex flex-col gap-3">
        {items.map((p) => (
          <li key={p.session_id} className="flex flex-col gap-3 rounded-lg border border-border bg-surface1 p-4">
            <p className="text-sm font-bold text-ink-primary">{dateAndTime(p.generated_at)}</p>
            <ul className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {DIMENSIONS.map((d) => (
                <li key={d.key} className="flex flex-col items-start gap-1">
                  <span className="text-xs text-ink-secondary">{d.label}</span>
                  <LevelChip level={p[d.key]} />
                </li>
              ))}
            </ul>
            <p className="text-sm text-ink-secondary">
              Correctness {pct(p.features.accuracy)} · Questions {p.features.total_questions}
            </p>
          </li>
        ))}
      </ol>

      <div className="flex flex-col gap-2 rounded-lg border border-border bg-surface1 p-4">
        <h3 className="text-base font-bold text-ink-primary">What the levels mean</h3>
        <ul className="flex flex-col gap-2">
          {LEGEND.map((entry) => (
            <li key={entry.tone} className={`rounded-lg border px-3 py-2 ${TONE_CHIP_CLASSES[entry.tone]}`}>
              <span className="block text-sm font-bold">{entry.words}</span>
              <span className="block text-xs">{entry.meaning}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col items-center text-center">
      <dt className="text-xs text-ink-secondary">{label}</dt>
      <dd className="text-base font-bold text-ink-primary">{value}</dd>
    </div>
  );
}
