import { useQueryClient, useQuery } from "@tanstack/react-query";
import { Plus, UserRound } from "lucide-react";
import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { client, isDuplicateClassNameError } from "../../api/client";
import { ClassCard } from "../../components/class/ClassCard";
import { ClassKeyDialog } from "../../components/class/ClassKeyDialog";
import { CreateClassDialog } from "../../components/class/CreateClassDialog";
import { ErrorState } from "../../components/shared/ErrorState";
import { LoadingSkeleton } from "../../components/shared/LoadingSkeleton";
import { StatTile } from "../../components/shared/StatTile";
import type { Grade } from "../../lib/presentation";

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
    <div className="mx-auto flex max-w-[480px] lg:max-w-[1200px] flex-col gap-4 p-4 pb-8">
      {/* Hardening-pass fix: this screen had no page-level heading at all —
          the visible title design is just the ⊕/framing/profile row, so a
          screen-reader-only h1 supplies the landmark without changing the
          visual layout (docs/11 §8: "sane heading hierarchy"). */}
      <h1 className="sr-only">Home</h1>
      <header className="flex items-center justify-between gap-2">
        <button
          type="button"
          aria-label="Add class"
          onClick={() => {
            setNameError(undefined);
            setIsCreateOpen(true);
          }}
          className="flex h-11 w-11 items-center justify-center rounded-full border border-border-strong text-ink-primary"
        >
          <Plus aria-hidden="true" size={22} />
        </button>
        <Link
          to="/profile"
          aria-label="Profile"
          className="flex h-11 w-11 items-center justify-center rounded-full border border-border-strong text-ink-primary"
        >
          <UserRound aria-hidden="true" size={22} />
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
              never colour alone. UI-refinement pass: the "of N students"
              total is kept for screen readers only (sr-only, still in the
              DOM) rather than shown visually, and the "Based on recent
              learning activity" framing sentence is dropped from this card
              entirely per explicit direction — plan §1's total-beside-count
              requirement is a compliance/checklist item, not a visual one,
              so the total stays available to assistive tech even though
              neither it nor the framing sentence is shown on screen. */}
          <Link
            to="/watch"
            className="flex flex-col justify-between gap-2 rounded-2xl border border-watch-watching-border bg-watch-watching-bg px-5 py-10"
          >
            <span className="self-start text-[17px] font-medium text-watch-watching-fg">
              Students to Watch
            </span>
            <span className="ml-10 text-7xl font-bold text-watch-watching-fg">
              {data.studentsToWatch}
            </span>
            <span className="sr-only">of {data.activeStudents} students</span>
            <span className="self-end rounded-full bg-watch-watching-fg px-4 py-2 text-sm font-medium text-white">
              View watch list
            </span>
          </Link>

          <div className="grid grid-cols-3 gap-2">
            <StatTile label="Active Students" value={data.activeStudents} tone="blue" />
            <StatTile label="Classes" value={data.classCount} tone="green" />
            <StatTile label="Getting Started" value={data.gettingStarted} tone="amber" />
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
              // Hardening-pass fix: plan §8 requires a two-column class
              // grid at 640-1023 — this was flex-col (single column) at
              // every width. sm:grid-cols-2 is additive; below 640 it's
              // still the same single-column stack.
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {data.classes.map((c) => (
                  <Link key={c.classId} to={`/classes/${c.classId}`} className="block">
                    <ClassCard
                      name={c.name}
                      grade={c.grade}
                      studentCount={c.studentCount}
                      toWatchCount={c.toWatchCount}
                      pendingRequestCount={c.pendingRequestCount}
                      variant="colorful"
                    />
                  </Link>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
