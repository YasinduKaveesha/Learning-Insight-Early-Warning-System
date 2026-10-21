import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { compd, compdRetry, type CompdStudentSummary } from "../../api/compdClient";
import { EmptyState } from "../../components/shared/EmptyState";
import { ErrorState } from "../../components/shared/ErrorState";
import { SearchField } from "../../components/shared/SearchField";
import {
  DIMENSIONS,
  STUDENT_FILTERS,
  avgTimeLabel,
  classLine,
  filterStudents,
  lastActivity,
  loadErrorMessage,
  needsSupport,
  pct,
  seconds,
  shownOf,
  studentName,
  weakestArea,
  type StudentFilter,
} from "../../lib/compdPresentation";
import { CompdPageSkeleton } from "./CompdPageSkeleton";
import { CompdTile, LevelChip } from "./CompdParts";

/**
 * The Students tab: compD's TeacherDashboard (TeacherDashboard.tsx), re-typed.
 * Every REAL child in the student app, from every class (owner Q10) -- so there
 * is no class selector, and each card says which class the child is in.
 */
export default function StudentsTab() {
  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ["compd", "dashboard"],
    queryFn: () => compd.getDashboard(),
    retry: compdRetry,
  });
  const [filter, setFilter] = useState<StudentFilter>("all");
  const [search, setSearch] = useState("");

  if (isPending) return <CompdPageSkeleton variant="tiles" label="Loading students" />;
  if (isError) return <ErrorState message={loadErrorMessage(error)} onRetry={() => refetch()} />;

  const { stats, students } = data;
  const visible = filterStudents(students, filter, search);

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <CompdTile label="Students" value={String(stats.total_students)} tone="blue" />
        <CompdTile label="Profiles" value={String(stats.students_with_profiles)} tone="green" />
        <CompdTile label="Avg accuracy" value={pct(stats.average_accuracy)} tone="green" />
        <CompdTile label="Need support" value={String(stats.needs_support_count)} tone="amber" />
      </div>

      <div className="flex flex-col gap-2">
        <div className="grid grid-cols-3 gap-2">
          {STUDENT_FILTERS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              aria-pressed={filter === value}
              onClick={() => setFilter(value)}
              className={`min-h-[44px] rounded-lg border px-2 text-sm font-bold ${
                filter === value
                  ? "border-watch-watching-border bg-watch-watching-bg text-watch-watching-fg"
                  : "border-border-strong bg-surface1 text-ink-secondary"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        {/* Added, not compD: a search by name, since the list spans every class. */}
        <SearchField label="Search students" value={search} onChange={setSearch} resultCount={visible.length} />
      </div>

      <div className="flex items-end justify-between gap-2 px-1">
        <div>
          <h2 className="text-base font-semibold text-ink-primary">Students</h2>
          <p className="text-sm text-ink-secondary">{shownOf(visible.length, students.length)}</p>
        </div>
        <p className="text-sm font-semibold text-ink-secondary">{avgTimeLabel(stats)}</p>
      </div>

      {visible.length === 0 ? (
        <EmptyState message="No students in this view." />
      ) : (
        <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {visible.map((student) => (
            <li key={student.student_id}>
              <StudentCard student={student} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** compD's StudentCard (TeacherDashboard.tsx:275-368). */
function StudentCard({ student }: { student: CompdStudentSummary }) {
  const perf = student.performance;
  const profile = student.latest_profile;
  const support = needsSupport(student);
  const profilePath = `/compd/students/${encodeURIComponent(student.student_id)}`;

  return (
    <article
      aria-label={studentName(student.name)}
      className={`flex flex-col gap-3 rounded-lg border bg-surface1 p-4 ${
        support ? "border-statAmber-border" : "border-border"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="truncate text-base font-bold text-ink-primary">{studentName(student.name)}</h3>
          {/* Added, not compD: the class and grade. */}
          <p className="text-sm text-ink-secondary">{classLine(student.classroom_name, student.grade)}</p>
        </div>
        <span
          className={`shrink-0 rounded-full border px-3 py-1 text-xs font-bold ${
            support
              ? "border-statAmber-border bg-statAmber-bg text-statAmber-fg"
              : "border-success bg-success-soft text-success-text"
          }`}
        >
          {support ? "Support" : "On track"}
        </span>
      </div>

      <div className="flex flex-col gap-1">
        <div className="flex justify-between text-sm">
          <span className="text-ink-secondary">Accuracy</span>
          <span className="font-bold text-ink-primary">{pct(perf.accuracy)}</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-surface2" aria-hidden="true">
          {/* compD's minimum of 5%, so an empty bar is still visibly a bar. */}
          <div
            className="h-full rounded-full bg-accent-blue"
            style={{ width: `${Math.max(5, Math.round(perf.accuracy * 100))}%` }}
          />
        </div>
      </div>

      <dl className="grid grid-cols-4 gap-1 text-center">
        <Metric label="Questions" value={String(perf.total_questions)} />
        <Metric label="Sessions" value={String(perf.completed_sessions)} />
        <Metric label="Avg time" value={seconds(perf.avg_response_time_sec)} />
        <Metric label="Hints" value={pct(perf.hint_rate)} />
      </dl>

      {profile ? (
        <ul className="grid grid-cols-2 gap-2">
          {DIMENSIONS.map((d) => (
            <li key={d.key} className="flex items-center justify-between gap-1 rounded-lg bg-surface2 px-2 py-1">
              <span className="text-xs text-ink-secondary">{d.label}</span>
              <LevelChip level={profile[d.key]} />
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-ink-secondary">No profile generated yet</p>
      )}

      <p className="text-sm">
        <span className="text-ink-secondary">Focus area: </span>
        <span className="font-bold text-ink-primary">{weakestArea(profile)}</span>
      </p>

      {perf.topics.length > 0 ? (
        <ul className="flex flex-wrap gap-2" aria-label="Top topics">
          {perf.topics.slice(0, 3).map((t) => (
            <li key={t.topic} className="rounded-full bg-secondary-soft px-3 py-1 text-xs font-bold text-secondary-foreground">
              {t.topic} {pct(t.accuracy)}
            </li>
          ))}
        </ul>
      ) : null}

      <p className="text-xs text-ink-secondary">{lastActivity(student.last_activity_date)}</p>

      <div className="grid grid-cols-2 gap-2">
        <Link
          to={profilePath}
          className="flex min-h-[44px] items-center justify-center rounded-lg bg-watch-watching-fg text-sm font-bold text-white"
        >
          View profile
        </Link>
        <Link
          to={`${profilePath}#history`}
          className="flex min-h-[44px] items-center justify-center rounded-lg border border-border-strong text-sm font-bold text-ink-primary"
        >
          History
        </Link>
      </div>
    </article>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <dt className="text-xs text-ink-secondary">{label}</dt>
      <dd className="text-sm font-bold text-ink-primary">{value}</dd>
    </div>
  );
}
