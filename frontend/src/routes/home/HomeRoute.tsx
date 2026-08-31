import { useQueryClient, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { client, isDuplicateClassNameError } from "../../api/client";
import { ClassCard } from "../../components/class/ClassCard";
import { ClassKeyDialog } from "../../components/class/ClassKeyDialog";
import { CreateClassDialog } from "../../components/class/CreateClassDialog";
import { DisclosureFooter } from "../../components/shared/DisclosureFooter";
import { ErrorState } from "../../components/shared/ErrorState";
import { FramingLine } from "../../components/shared/FramingLine";
import { LoadingSkeleton } from "../../components/shared/LoadingSkeleton";
import { StatTile } from "../../components/shared/StatTile";
import { SNAPSHOT_FRAMING, type Grade } from "../../lib/presentation";

const GETTING_STARTED_INFO =
  "These students are still building their learning history. They need at least 3 completed sessions before the system can identify a clear pattern.";

/**
 * Home — the teacher-level dashboard (plan §4.1). The watch card is the
 * largest element on the page: it is why the application exists.
 */
export default function HomeRoute() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ["home"],
    queryFn: () => client.getHome(),
  });

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [nameError, setNameError] = useState<string | undefined>(undefined);
  // Populated on successful creation; ClassKeyDialog opens the moment this
  // is set, and CreateClassDialog closes at the same time — "Created →
  // Class Key" happens as one transition, per plan §4.7's flow.
  const [createdClass, setCreatedClass] = useState<
    { classId: string; className: string; classKey: string } | undefined
  >(undefined);

  async function handleCreateSubmit(name: string, grade: Grade) {
    setNameError(undefined);
    try {
      const result = await client.createClass(name, grade);
      setIsCreateOpen(false);
      setCreatedClass(result);
      // The new class must appear in "Your Classes" and the stat tiles
      // immediately — refetch rather than hand-patch the cache, since the
      // mock (and eventually the real API) is the source of truth for
      // counts derived from the roster.
      void queryClient.invalidateQueries({ queryKey: ["home"] });
    } catch (e) {
      if (isDuplicateClassNameError(e)) {
        setNameError(e.message);
      } else {
        throw e;
      }
    }
  }

  return (
    <div className="mx-auto flex max-w-[480px] flex-col gap-4 p-4 pb-8">
      <header className="flex items-center justify-between gap-2">
        <button
          type="button"
          aria-label="Add class"
          onClick={() => {
            setNameError(undefined);
            setIsCreateOpen(true);
          }}
          className="flex h-11 w-11 items-center justify-center rounded-full border border-border-strong text-xl text-ink-primary"
        >
          ⊕
        </button>
        <FramingLine />
        <Link
          to="/profile"
          aria-label="Profile"
          className="flex h-11 w-11 items-center justify-center rounded-full border border-border-strong text-ink-primary"
        >
          ◯
        </Link>
      </header>

      <CreateClassDialog
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        onSubmit={handleCreateSubmit}
        nameError={nameError}
      />
      {createdClass ? (
        <ClassKeyDialog
          isOpen={true}
          onClose={() => setCreatedClass(undefined)}
          className={createdClass.className}
          classKey={createdClass.classKey}
          onGoToClass={() => {
            const classId = createdClass.classId;
            setCreatedClass(undefined);
            navigate(`/classes/${classId}`);
          }}
        />
      ) : null}

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
            <h2 className="px-1 py-2 text-base font-semibold text-ink-primary">Your Classes</h2>
            {data.classes.length === 0 ? (
              <button
                type="button"
                onClick={() => {
                  setNameError(undefined);
                  setIsCreateOpen(true);
                }}
                className="flex min-h-[44px] w-full items-center justify-center rounded-lg border-2 border-dashed border-border-strong p-6 text-sm font-medium text-ink-primary"
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
