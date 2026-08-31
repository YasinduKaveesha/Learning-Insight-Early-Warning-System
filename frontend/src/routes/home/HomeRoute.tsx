import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { client } from "../../api/client";
import { ClassCard } from "../../components/class/ClassCard";
import { DisclosureFooter } from "../../components/shared/DisclosureFooter";
import { ErrorState } from "../../components/shared/ErrorState";
import { FramingLine } from "../../components/shared/FramingLine";
import { LoadingSkeleton } from "../../components/shared/LoadingSkeleton";
import { StatTile } from "../../components/shared/StatTile";
import { SNAPSHOT_FRAMING } from "../../lib/presentation";

const GETTING_STARTED_INFO =
  "These students are still building their learning history. They need at least 3 completed sessions before the system can identify a clear pattern.";

/**
 * Home — the teacher-level dashboard (plan §4.1). The watch card is the
 * largest element on the page: it is why the application exists.
 */
export default function HomeRoute() {
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ["home"],
    queryFn: () => client.getHome(),
  });

  return (
    <div className="mx-auto flex max-w-[480px] flex-col gap-4 p-4 pb-8">
      <header className="flex items-center justify-between gap-2">
        {/* The dialog behind this is Step 6 — the 44px target exists, inert for now. */}
        <button
          type="button"
          aria-label="Add class"
          className="flex h-11 w-11 items-center justify-center rounded-full border border-slate-300 text-xl text-slate-700"
        >
          ⊕
        </button>
        <FramingLine />
        <Link
          to="/profile"
          aria-label="Profile"
          className="flex h-11 w-11 items-center justify-center rounded-full border border-slate-300 text-slate-700"
        >
          ◯
        </Link>
      </header>

      {isPending ? (
        <>
          <LoadingSkeleton rows={1} rowHeight={160} />
          <LoadingSkeleton rows={1} rowHeight={80} />
          <LoadingSkeleton rows={3} rowHeight={64} />
        </>
      ) : isError ? (
        <ErrorState
          message="Couldn't load your dashboard. Check your connection and try again."
          onRetry={() => refetch()}
        />
      ) : (
        <>
          {/* The watch card — largest element on the page, icon AND text,
              never colour alone. The total is mandatory beside the count
              (plan §1): the flag saturates from ~4% early to ~86% late in
              the study, and the fraction is what lets a teacher see when
              the list has stopped being selective. */}
          <Link
            to="/watch"
            className="flex flex-col gap-1 rounded-2xl border border-watch-watching-border bg-watch-watching-bg p-5"
          >
            <div className="flex items-center gap-2 text-sm font-medium text-watch-watching-fg">
              <span aria-hidden="true" className="text-xl">
                ◐
              </span>
              <span>Students to Watch</span>
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-5xl font-bold text-watch-watching-fg">
                {data.studentsToWatch}
              </span>
              <span className="text-sm text-watch-watching-fg">
                of {data.activeStudents} students
              </span>
            </div>
            <p className="text-xs text-watch-watching-fg">{SNAPSHOT_FRAMING}</p>
            <span className="mt-1 text-sm font-medium text-watch-watching-fg">
              View watch list →
            </span>
          </Link>

          <div className="grid grid-cols-3 gap-2">
            <StatTile label="Active Students" value={data.activeStudents} />
            <StatTile label="Classes" value={data.classCount} />
            <StatTile
              label="Getting Started"
              value={data.gettingStarted}
              infoText={GETTING_STARTED_INFO}
            />
          </div>

          <section>
            <h2 className="px-1 py-2 text-base font-semibold text-slate-900">Your Classes</h2>
            {data.classes.length === 0 ? (
              <button
                type="button"
                className="flex min-h-[44px] w-full items-center justify-center rounded-lg border-2 border-dashed border-slate-300 p-6 text-sm font-medium text-slate-700"
              >
                Create your first class to get started.
              </button>
            ) : (
              <div className="flex flex-col gap-2">
                {data.classes.map((c) => (
                  <Link key={c.classId} to={`/classes/${c.classId}`} className="block">
                    <ClassCard
                      name={c.name}
                      grade={c.grade}
                      studentCount={c.studentCount}
                      toWatchCount={c.toWatchCount}
                    />
                  </Link>
                ))}
              </div>
            )}
          </section>

          <DisclosureFooter disclosure={data.disclosure} />
        </>
      )}
    </div>
  );
}
