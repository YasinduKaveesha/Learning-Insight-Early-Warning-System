import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useId, useState, type FormEvent } from "react";
import {
  COMPD_DIFFICULTIES,
  COMPD_TOPICS,
  compd,
  isCompdError,
  type CompdDifficulty,
  type CompdQuestionInput,
  type CompdTopic,
} from "../../api/compdClient";
import { SelectField } from "../../components/shared/SelectField";
import {
  AI_UNAVAILABLE,
  AI_UNUSABLE,
  DUPLICATE_CODE,
  LOAD_FAILED,
  SAVE_FAILED,
  parseOptions,
  withAnswer,
} from "../../lib/compdPresentation";
import { CompdPageSkeleton } from "./CompdPageSkeleton";

const INPUT = "min-h-[44px] w-full rounded-lg border border-border-strong bg-surface1 px-3 text-base";
const TOPIC_OPTIONS = COMPD_TOPICS.map((t) => ({ value: t, label: t }));
const DIFFICULTY_OPTIONS = COMPD_DIFFICULTIES.map((d) => ({ value: d, label: d }));

interface Draft {
  localId: string;
  input: CompdQuestionInput;
  optionsText: string;
  status: "editing" | "saving" | "saved";
  error?: string;
}

/**
 * compD's AIGenerateScreen as a panel on the Questions tab: choose a topic,
 * difficulty, count and optional instructions; review the drafts; edit any;
 * save one at a time or all together. Drafts are NOT in the bank until saved --
 * each save is one createQuestion, as compD's "Save" and "Save all" were.
 */
export function AiPanel({ onCreateManually }: { onCreateManually: () => void }) {
  const ids = useId();
  const queryClient = useQueryClient();
  const [topic, setTopic] = useState<CompdTopic>("Addition");
  const [difficulty, setDifficulty] = useState<CompdDifficulty>("Easy");
  const [count, setCount] = useState("5");
  const [instructions, setInstructions] = useState("");
  const [drafts, setDrafts] = useState<Draft[]>([]);

  const generate = useMutation({
    mutationFn: () =>
      compd.draftQuestions({
        topic,
        difficulty,
        // compD's clamp: 1-10, 5 when the field is not a number.
        count: Math.max(1, Math.min(10, Number(count) || 5)),
        instructions: instructions.trim() || undefined,
      }),
    onSuccess: (inputs) =>
      setDrafts(
        inputs.map((input, i) => ({
          localId: `draft-${Date.now()}-${i}`,
          input,
          optionsText: input.options?.join(", ") ?? "",
          status: "editing",
        })),
      ),
  });

  function update(localId: string, patch: Partial<Draft>) {
    setDrafts((prev) => prev.map((d) => (d.localId === localId ? { ...d, ...patch } : d)));
  }

  async function save(draft: Draft): Promise<boolean> {
    const answer = draft.input.correct_answer.trim();
    if (!draft.input.question_text.trim() || !answer) {
      update(draft.localId, { error: "Write the question and the answer." });
      return false;
    }
    const options = withAnswer(parseOptions(draft.optionsText), answer);
    if (!options.ok) {
      update(draft.localId, { error: options.error });
      return false;
    }
    update(draft.localId, { status: "saving", error: undefined });
    try {
      await compd.createQuestion({
        ...draft.input,
        question_text: draft.input.question_text.trim(),
        correct_answer: answer,
        options: options.options,
      });
      update(draft.localId, { status: "saved" });
      void queryClient.invalidateQueries({ queryKey: ["compd", "questions"] });
      return true;
    } catch (error) {
      const message = isCompdError(error) && error.status === 409 ? DUPLICATE_CODE : SAVE_FAILED;
      update(draft.localId, { status: "editing", error: message });
      return false;
    }
  }

  async function saveAll() {
    // One at a time, in order, as compD's Save all did; one failure does not stop the rest.
    for (const draft of drafts) {
      if (draft.status === "editing") await save(draft);
    }
  }

  function handleGenerate(e: FormEvent) {
    e.preventDefault();
    setDrafts([]);
    generate.mutate();
  }

  const unsaved = drafts.filter((d) => d.status !== "saved").length;

  return (
    <section aria-labelledby={`${ids}-heading`} className="flex flex-col gap-4 rounded-lg border border-suggestionPurple-border bg-suggestionPurple-bg p-4">
      <h3 id={`${ids}-heading`} className="text-base font-bold text-suggestionPurple-fg">
        Generate with AI
      </h3>

      <form className="flex flex-col gap-3" onSubmit={handleGenerate} noValidate>
        <SelectField
          label="Topic"
          value={topic}
          onChange={(value) => value && setTopic(value as CompdTopic)}
          options={TOPIC_OPTIONS}
          placeholder="Choose a topic"
        />
        <SelectField
          label="Difficulty"
          value={difficulty}
          onChange={(value) => value && setDifficulty(value as CompdDifficulty)}
          options={DIFFICULTY_OPTIONS}
          placeholder="Choose a difficulty"
        />
        <div className="flex flex-col gap-1">
          <label htmlFor={`${ids}-count`} className="text-sm font-bold text-ink-primary">
            How many questions (1-10)
          </label>
          <input
            id={`${ids}-count`}
            type="number"
            min={1}
            max={10}
            value={count}
            onChange={(e) => setCount(e.target.value)}
            className={INPUT}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor={`${ids}-instructions`} className="text-sm font-bold text-ink-primary">
            Instructions (optional)
          </label>
          <textarea
            id={`${ids}-instructions`}
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
            placeholder="e.g. 'Use word problems with fruits'"
            maxLength={300}
            rows={2}
            aria-describedby={`${ids}-instructions-hint`}
            className={`${INPUT} py-2`}
          />
          {/* Added, not compD (owner-approved, plan 03 v4.2): what is typed here
              is sent to the AI service as written. */}
          <p id={`${ids}-instructions-hint`} className="text-xs text-ink-secondary">
            Don&apos;t include children&apos;s names or details.
          </p>
        </div>
        <button
          type="submit"
          disabled={generate.isPending}
          className="min-h-[44px] rounded-lg bg-suggestionPurple-accept text-sm font-bold text-white disabled:opacity-60"
        >
          {generate.isPending ? "Generating…" : "Generate"}
        </button>
      </form>

      {generate.isPending ? <CompdPageSkeleton variant="list" label="Generating questions" /> : null}

      {generate.isError ? (
        <div role="alert" className="flex flex-col gap-2 rounded-lg border border-border bg-surface1 p-3">
          <p className="text-sm text-ink-primary">{draftErrorMessage(generate.error)}</p>
          {isCompdError(generate.error) && generate.error.status === 503 ? (
            <button
              type="button"
              onClick={onCreateManually}
              className="min-h-[44px] rounded-lg border border-border-strong text-sm font-bold text-ink-primary"
            >
              Create manually
            </button>
          ) : null}
        </div>
      ) : null}

      {drafts.length > 0 ? (
        <div className="flex flex-col gap-3">
          <ol className="flex flex-col gap-3" aria-label="Question drafts">
            {drafts.map((draft, i) => (
              <li key={draft.localId} className="flex flex-col gap-2 rounded-lg border border-border bg-surface1 p-3">
                <p className="text-xs font-bold text-ink-secondary">
                  Draft {i + 1} · {draft.input.topic} · {draft.input.difficulty}
                </p>
                <label className="flex flex-col gap-1 text-sm font-bold text-ink-primary">
                  Question
                  <textarea
                    value={draft.input.question_text}
                    disabled={draft.status !== "editing"}
                    onChange={(e) => update(draft.localId, { input: { ...draft.input, question_text: e.target.value } })}
                    rows={2}
                    className={`${INPUT} py-2 font-normal`}
                  />
                </label>
                <label className="flex flex-col gap-1 text-sm font-bold text-ink-primary">
                  Answer
                  <input
                    value={draft.input.correct_answer}
                    disabled={draft.status !== "editing"}
                    onChange={(e) => update(draft.localId, { input: { ...draft.input, correct_answer: e.target.value } })}
                    className={`${INPUT} font-normal`}
                  />
                </label>
                <label className="flex flex-col gap-1 text-sm font-bold text-ink-primary">
                  Options (comma-separated)
                  <input
                    value={draft.optionsText}
                    disabled={draft.status !== "editing"}
                    onChange={(e) => update(draft.localId, { optionsText: e.target.value })}
                    className={`${INPUT} font-normal`}
                  />
                </label>
                {draft.error ? (
                  <p role="alert" className="text-sm font-bold text-danger-text">
                    {draft.error}
                  </p>
                ) : null}
                {draft.status === "saved" ? (
                  <p className="text-sm font-bold text-success-text">Saved</p>
                ) : (
                  <button
                    type="button"
                    disabled={draft.status === "saving"}
                    onClick={() => void save(draft)}
                    className="min-h-[44px] rounded-lg bg-watch-watching-fg text-sm font-bold text-white disabled:opacity-60"
                  >
                    {draft.status === "saving" ? "Saving…" : "Save"}
                  </button>
                )}
              </li>
            ))}
          </ol>
          {unsaved > 0 ? (
            <button
              type="button"
              onClick={() => void saveAll()}
              className="min-h-[44px] rounded-lg bg-suggestionPurple-accept text-sm font-bold text-white"
            >
              Save all ({unsaved})
            </button>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function draftErrorMessage(error: unknown): string {
  if (isCompdError(error) && error.status === 503) return AI_UNAVAILABLE;
  if (isCompdError(error) && error.status === 422) return AI_UNUSABLE;
  return LOAD_FAILED;
}
