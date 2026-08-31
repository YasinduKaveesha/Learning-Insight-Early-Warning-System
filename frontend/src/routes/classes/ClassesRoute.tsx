import { useQueryClient, useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { client, isDuplicateClassNameError } from "../../api/client";
import { ClassCard } from "../../components/class/ClassCard";
import { ClassKeyDialog } from "../../components/class/ClassKeyDialog";
import { CreateClassDialog } from "../../components/class/CreateClassDialog";
import { ErrorState } from "../../components/shared/ErrorState";
import { LoadingSkeleton } from "../../components/shared/LoadingSkeleton";
import type { Grade } from "../../lib/presentation";

/**
 * All Classes (plan §3: `/classes`). Plan §4 has no wireframe for this
 * screen — it names the route but never mocks it up. `GET .../home` (the
 * only source for a teacher's class list) already returns every class, not
 * a subset, so Home's "Your Classes" and this screen render identical data;
 * the only real distinction is that this is the complete list on its own
 * screen, addressable from the bottom tab bar, rather than a section inside
 * the wider Home dashboard. Built here with the same class-card shape and
 * the same create-class flow Home already uses (reusing both components
 * outright, not forking near-copies) and the plan §8 four states.
 */
export default function ClassesRoute() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ["home"],
    queryFn: () => client.getHome(),
  });

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [nameError, setNameError] = useState<string | undefined>(undefined);
  const [createdClass, setCreatedClass] = useState<
    { classId: string; className: string; classKey: string } | undefined
  >(undefined);

  function openCreate() {
    setNameError(undefined);
    setIsCreateOpen(true);
  }

  async function handleCreateSubmit(name: string, grade: Grade) {
    setNameError(undefined);
    try {
      const result = await client.createClass(name, grade);
      setIsCreateOpen(false);
      setCreatedClass(result);
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
      <header className="flex items-center justify-between gap-2">
        <h1 className="text-base font-semibold text-ink-primary">All Classes</h1>
        <button
          type="button"
          aria-label="Add class"
          onClick={openCreate}
          className="flex h-11 w-11 items-center justify-center rounded-full border border-border-strong text-ink-primary"
        >
          <Plus aria-hidden="true" size={22} />
        </button>
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
        <LoadingSkeleton rows={4} rowHeight={64} />
      ) : isError ? (
        <ErrorState
          message="Couldn't load your classes. Check your connection and try again."
          onRetry={() => refetch()}
        />
      ) : data.classes.length === 0 ? (
        <button
          type="button"
          onClick={openCreate}
          className="flex min-h-[44px] w-full items-center justify-center rounded-lg border-2 border-dashed border-border-strong p-6 text-sm font-medium text-ink-primary"
        >
          Create your first class to get started.
        </button>
      ) : (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
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
    </div>
  );
}
