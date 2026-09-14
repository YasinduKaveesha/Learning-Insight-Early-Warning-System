import { useQueryClient, useQuery } from "@tanstack/react-query";
import { Plus, UserRound } from "lucide-react";
import { useLayoutEffect, useRef, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { client, isDuplicateClassNameError } from "../../api/client";
import { ClassCard } from "../../components/class/ClassCard";
import { ClassKeyDialog } from "../../components/class/ClassKeyDialog";
import { CreateClassDialog } from "../../components/class/CreateClassDialog";
import { DeleteClassDialog } from "../../components/class/DeleteClassDialog";
import { SwipeToDelete } from "../../components/class/SwipeToDelete";
import { ErrorState } from "../../components/shared/ErrorState";
import { LoadingSkeleton } from "../../components/shared/LoadingSkeleton";
import { StatTile } from "../../components/shared/StatTile";
import { sortClassesByWatchShare, type Grade } from "../../lib/presentation";

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

  // Swipe-to-delete (2026-09-14): at most one card is swiped open at a time,
  // and the class being deleted is held while its confirmation dialog is up.
  const [swipedClassId, setSwipedClassId] = useState<string | null>(null);
  const [classToDelete, setClassToDelete] = useState<
    { classId: string; name: string } | null
  >(null);

  async function handleDeleteConfirmed(confirmationName: string) {
    if (!classToDelete) return;
    const { classId } = classToDelete;
    // A failure rejects into the dialog, which shows it and stays open.
    await client.deleteClass(classId, confirmationName);
    setClassToDelete(null);
    setSwipedClassId(null);
    queryClient.removeQueries({ queryKey: ["cohort", classId] });
    queryClient.removeQueries({ queryKey: ["classWatch", classId] });
    queryClient.removeQueries({ queryKey: ["classReports", classId] });
    queryClient.removeQueries({ queryKey: ["joinRequests", classId] });
    // The class's learners leave every count; the watch list must drop them too.
    void queryClient.invalidateQueries({ queryKey: ["home"] });
    void queryClient.invalidateQueries({ queryKey: ["watch"] });
  }

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

  // The pinned block (buttons + watch card) changes height with the number it
  // shows and the screen width, so "Your Classes" reads it rather than
  // guessing: it must stick exactly at the pinned block's bottom edge, or
  // class cards would show through a gap or hide behind an overlap.
  const pinnedRef = useRef<HTMLDivElement>(null);
  const [pinnedHeight, setPinnedHeight] = useState(0);
  useLayoutEffect(() => {
    const node = pinnedRef.current;
    if (!node) return;
    const measure = () => setPinnedHeight(node.getBoundingClientRect().height);
    measure();
    // ResizeObserver is absent in some test environments; a one-off
    // measurement is still correct there.
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  });

  return (
    // No vertical padding here: the pinned block carries its own, so its
    // background can cover the content that scrolls up beneath it.
    <div className="mx-auto flex max-w-[480px] lg:max-w-[1200px] flex-col px-4 pb-8">
      {/* Hardening-pass fix: this screen had no page-level heading at all —
          the visible title design is just the ⊕/framing/profile row, so a
          screen-reader-only h1 supplies the landmark without changing the
          visual layout (docs/11 §8: "sane heading hierarchy"). */}
      <h1 className="sr-only">Home</h1>
      {/* PINNED: the buttons and the watch card stay at the top while the page
          scrolls. The three stat tiles below slide up UNDER this block, and
          its page-coloured background is what hides them -- so it spans the
          column's padding (-mx-4 px-4) and carries the gap beneath the card
          (pb-4), leaving no strip for them to show through. */}
      <div
        ref={pinnedRef}
        className="sticky top-0 z-20 -mx-4 flex flex-col gap-4 bg-background px-4 pb-4 pt-4"
      >
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
        {data ? (
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
          </>
        ) : null}
      </div>

      <CreateClassDialog
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        onSubmit={handleCreateSubmit}
        nameError={nameError}
      />
      <DeleteClassDialog
        isOpen={classToDelete !== null}
        className={classToDelete?.name ?? ""}
        onConfirm={handleDeleteConfirmed}
        onCancel={() => {
          setClassToDelete(null);
          setSwipedClassId(null);
        }}
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
        <div className="flex flex-col gap-4">
          <LoadingSkeleton rows={1} rowHeight={160} />
          <LoadingSkeleton rows={1} rowHeight={80} />
          <LoadingSkeleton rows={3} rowHeight={64} />
        </div>
      ) : isError ? (
        <ErrorState
          message="Couldn't load your dashboard. Check your connection and try again."
          onRetry={() => refetch()}
        />
      ) : (
        <>


          <div className="grid grid-cols-3 gap-2">
            <StatTile label="Active Students" value={data.activeStudents} tone="blue" />
            <StatTile label="Classes" value={data.classCount} tone="green" />
            <StatTile label="Getting Started" value={data.gettingStarted} tone="amber" />
          </div>

          <section className="mt-4">
            {/* Rises with the page until it meets the pinned block, then stays
                there; only the class cards scroll beneath it after that. Its
                `top` is the pinned block's measured height, not a guess. */}
            <h2
              style={{ top: pinnedHeight }}
              className="sticky z-10 -mx-4 bg-background px-5 py-2 text-base font-semibold text-ink-primary"
            >
              Your Classes
            </h2>
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
                {sortClassesByWatchShare(data.classes).map((c) => (
                  <SwipeToDelete
                    key={c.classId}
                    label={c.name}
                    isOpen={swipedClassId === c.classId}
                    onOpenChange={(open) => setSwipedClassId(open ? c.classId : null)}
                    onDelete={() => setClassToDelete({ classId: c.classId, name: c.name })}
                  >
                    <Link to={`/classes/${c.classId}`} className="block" draggable={false}>
                      <ClassCard
                        name={c.name}
                        grade={c.grade}
                        studentCount={c.studentCount}
                        toWatchCount={c.toWatchCount}
                        pendingRequestCount={c.pendingRequestCount}
                        variant="colorful"
                      />
                    </Link>
                  </SwipeToDelete>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
