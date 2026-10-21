import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useRef, useState } from "react";
import {
  COMPD_DIFFICULTIES,
  COMPD_TOPICS,
  compd,
  compdRetry,
  type CompdDifficulty,
  type CompdQuestion,
  type CompdTopic,
} from "../../api/compdClient";
import { Dialog } from "../../components/shared/Dialog";
import { EmptyState } from "../../components/shared/EmptyState";
import { ErrorState } from "../../components/shared/ErrorState";
import { SelectField } from "../../components/shared/SelectField";
import { SAVE_FAILED, loadErrorMessage, questionCount } from "../../lib/compdPresentation";
import { AiPanel } from "./AiPanel";
import { CompdPageSkeleton } from "./CompdPageSkeleton";
import { QuestionForm } from "./QuestionForm";

const TOPIC_FILTER = COMPD_TOPICS.map((t) => ({ value: t, label: t }));
const DIFFICULTY_FILTER = COMPD_DIFFICULTIES.map((d) => ({ value: d, label: d }));

type FormState = { question?: CompdQuestion } | null;

/**
 * The Questions tab: compD's QuestionLandingScreen (the count and three actions)
 * and EditQuestionsScreen (the list), with ManualCreateScreen and the inline edit
 * as one Dialog, and AIGenerateScreen as a panel on the same tab.
 *
 * One shared bank (Q8): every teacher sees and changes the same questions. No
 * line about who uses them (Q4) -- they do not reach the children's activity (Q7).
 */
export default function QuestionsTab() {
  const ids = useId();
  const queryClient = useQueryClient();
  const listRef = useRef<HTMLDivElement>(null);
  const [topic, setTopic] = useState<CompdTopic | "">("");
  const [difficulty, setDifficulty] = useState<CompdDifficulty | "">("");
  const [form, setForm] = useState<FormState>(null);
  const [aiOpen, setAiOpen] = useState(false);
  const [toDelete, setToDelete] = useState<CompdQuestion | null>(null);

  const filtered = topic !== "" || difficulty !== "";
  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ["compd", "questions", topic, difficulty],
    queryFn: () =>
      compd.listQuestions({ topic: topic || undefined, difficulty: difficulty || undefined }),
    retry: compdRetry,
  });

  const remove = useMutation({
    mutationFn: (questionId: string) => compd.deleteQuestion(questionId),
    onSuccess: () => {
      setToDelete(null);
      void queryClient.invalidateQueries({ queryKey: ["compd", "questions"] });
    },
  });

  const openCreate = () => setForm({});

  function scrollToList() {
    const list = listRef.current;
    // Guarded like SelectField's: jsdom has no scrollIntoView.
    if (list && typeof list.scrollIntoView === "function") list.scrollIntoView({ block: "start" });
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface1 p-4">
        <p className="text-base font-bold text-ink-primary">
          {data ? (filtered ? `${data.length} shown` : questionCount(data.length)) : "Question bank"}
        </p>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          <button
            type="button"
            onClick={openCreate}
            className="min-h-[44px] rounded-lg bg-watch-watching-fg px-3 text-sm font-bold text-white"
          >
            Create manually
          </button>
          <button
            type="button"
            aria-expanded={aiOpen}
            onClick={() => setAiOpen((open) => !open)}
            className="min-h-[44px] rounded-lg bg-suggestionPurple-accept px-3 text-sm font-bold text-white"
          >
            Generate with AI
          </button>
          <button
            type="button"
            onClick={scrollToList}
            className="min-h-[44px] rounded-lg border border-border-strong px-3 text-sm font-bold text-ink-primary"
          >
            Edit existing questions
          </button>
        </div>
      </div>

      {aiOpen ? <AiPanel onCreateManually={openCreate} /> : null}

      <div ref={listRef} className="flex scroll-mt-40 flex-col gap-3">
        <h2 id={`${ids}-list`} className="px-1 text-base font-semibold text-ink-primary">
          Questions
        </h2>
        {/* Added, not compD: filters, since the bank is shared by every teacher. */}
        <div className="grid grid-cols-2 gap-2">
          <SelectField
            label="Topic"
            value={topic}
            onChange={(value) => setTopic(value as CompdTopic | "")}
            options={TOPIC_FILTER}
            placeholder="All topics"
          />
          <SelectField
            label="Difficulty"
            value={difficulty}
            onChange={(value) => setDifficulty(value as CompdDifficulty | "")}
            options={DIFFICULTY_FILTER}
            placeholder="All levels"
          />
        </div>

        {isPending ? (
          <CompdPageSkeleton variant="list" label="Loading questions" />
        ) : isError ? (
          <ErrorState message={loadErrorMessage(error)} onRetry={() => refetch()} />
        ) : data.length === 0 ? (
          filtered ? (
            <EmptyState message="No questions match these filters." />
          ) : (
            <div className="flex flex-col gap-2">
              <EmptyState message="No questions yet. Create one, or generate some with AI." />
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={openCreate}
                  className="min-h-[44px] rounded-lg border border-border-strong text-sm font-bold text-ink-primary"
                >
                  Create manually
                </button>
                <button
                  type="button"
                  onClick={() => setAiOpen(true)}
                  className="min-h-[44px] rounded-lg border border-border-strong text-sm font-bold text-ink-primary"
                >
                  Generate with AI
                </button>
              </div>
            </div>
          )
        ) : (
          <ul aria-labelledby={`${ids}-list`} className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {data.map((q) => (
              <li key={q.id} className="flex flex-col gap-2 rounded-lg border border-border bg-surface1 p-4">
                <div className="flex flex-wrap items-center gap-2 text-xs font-bold">
                  {q.question_code ? <span className="text-ink-secondary">{q.question_code}</span> : null}
                  <span className="rounded-full bg-secondary-soft px-2 py-0.5 text-secondary-foreground">{q.topic}</span>
                  <span className="rounded-full bg-surface2 px-2 py-0.5 text-ink-secondary">{q.difficulty}</span>
                </div>
                <p className="text-base text-ink-primary">{q.question_text}</p>
                <p className="text-sm text-ink-secondary">Answer: {q.correct_answer}</p>
                {q.options ? (
                  <p className="text-sm text-ink-secondary">Options: {q.options.join(", ")}</p>
                ) : null}
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    aria-label={`Edit "${q.question_text}"`}
                    onClick={() => setForm({ question: q })}
                    className="min-h-[44px] rounded-lg border border-border-strong text-sm font-bold text-ink-primary"
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    aria-label={`Delete "${q.question_text}"`}
                    onClick={() => setToDelete(q)}
                    className="min-h-[44px] rounded-lg border border-danger text-sm font-bold text-danger-text"
                  >
                    Delete
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <Dialog
        isOpen={form !== null}
        onClose={() => setForm(null)}
        titleId={`${ids}-form`}
        title={form?.question ? "Edit question" : "Create a question"}
      >
        {form !== null ? (
          <QuestionForm key={form.question?.id ?? "new"} question={form.question} onDone={() => setForm(null)} />
        ) : null}
      </Dialog>

      <Dialog
        isOpen={toDelete !== null}
        onClose={() => setToDelete(null)}
        titleId={`${ids}-delete`}
        title="Delete question"
        placement="center"
      >
        <div className="flex flex-col gap-4">
          <p className="text-sm text-ink-primary">
            Are you sure you want to delete &ldquo;{toDelete?.question_text}&rdquo;? This can&apos;t be undone.
          </p>
          {remove.isError ? (
            <p role="alert" className="text-sm font-bold text-danger-text">
              {SAVE_FAILED}
            </p>
          ) : null}
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => setToDelete(null)}
              className="min-h-[44px] rounded-lg border border-border-strong text-sm font-bold text-ink-primary"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={remove.isPending}
              onClick={() => toDelete && remove.mutate(toDelete.id)}
              className="min-h-[44px] rounded-lg bg-danger text-sm font-bold text-danger-foreground disabled:opacity-60"
            >
              Delete
            </button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
