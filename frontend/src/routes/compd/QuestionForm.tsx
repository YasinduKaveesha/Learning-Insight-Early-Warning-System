import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useId, useState, type FormEvent, type ReactNode } from "react";
import {
  COMPD_DIFFICULTIES,
  COMPD_TOPICS,
  compd,
  isCompdError,
  type CompdDifficulty,
  type CompdQuestion,
  type CompdTopic,
} from "../../api/compdClient";
import { SelectField } from "../../components/shared/SelectField";
import { DUPLICATE_CODE, SAVE_FAILED, parseOptions, withAnswer } from "../../lib/compdPresentation";

const INPUT = "min-h-[44px] w-full rounded-lg border border-border-strong bg-surface1 px-3 text-base";
const TOPIC_OPTIONS = COMPD_TOPICS.map((t) => ({ value: t, label: t }));

type Errors = Partial<Record<"code" | "text" | "answer" | "options" | "form", string>>;

/**
 * One form for both compD's ManualCreateScreen (create) and its inline edit
 * (EditQuestionsScreen.tsx). Edit changes only what compD's edit changed --
 * question, answer, options, difficulty -- and shows the code and topic as text.
 *
 * As in compD, the answer is added to the options when they leave it out; then
 * the bank's 2-6 rule applies, and "only the answer" asks for another
 * option rather than saving a one-option question (a difference from compD).
 */
export function QuestionForm({
  question,
  onDone,
}: {
  /** Absent: create. Present: edit this question. */
  question?: CompdQuestion;
  onDone: () => void;
}) {
  const ids = useId();
  const queryClient = useQueryClient();
  const editing = question !== undefined;

  const [code, setCode] = useState("");
  const [topic, setTopic] = useState<CompdTopic>("Addition");
  const [difficulty, setDifficulty] = useState<CompdDifficulty>(question?.difficulty ?? "Easy");
  const [text, setText] = useState(question?.question_text ?? "");
  const [answer, setAnswer] = useState(question?.correct_answer ?? "");
  const [optionsText, setOptionsText] = useState(question?.options?.join(", ") ?? "");
  const [errors, setErrors] = useState<Errors>({});

  const save = useMutation({
    mutationFn: async (options: string[] | null) => {
      if (question) {
        return compd.updateQuestion(question.id, {
          question_text: text.trim(),
          correct_answer: answer.trim(),
          difficulty,
          // compD sent no options when the field was left empty: the stored ones stay.
          ...(options ? { options } : {}),
        });
      }
      return compd.createQuestion({
        question_code: code.trim() || null,
        topic,
        difficulty,
        question_text: text.trim(),
        correct_answer: answer.trim(),
        options,
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["compd", "questions"] });
      onDone();
    },
    onError: (error) => {
      if (isCompdError(error) && error.status === 409) setErrors({ code: DUPLICATE_CODE });
      else setErrors({ form: SAVE_FAILED });
    },
  });

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const next: Errors = {};
    if (!text.trim()) next.text = "Write the question.";
    if (!answer.trim()) next.answer = "Write the answer.";
    const options = withAnswer(parseOptions(optionsText), answer.trim());
    if (!options.ok) next.options = options.error;
    setErrors(next);
    if (Object.keys(next).length > 0 || !options.ok) return;
    save.mutate(options.options);
  }

  return (
    <form className="flex flex-col gap-4" onSubmit={handleSubmit} noValidate>
      {editing ? (
        <p className="text-sm text-ink-secondary">
          {question.question_code ? `${question.question_code} · ` : ""}
          {question.topic}
        </p>
      ) : (
        <>
          <Field id={`${ids}-code`} label="Question code" error={errors.code}>
            <input
              id={`${ids}-code`}
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="Optional, e.g. ADD-021"
              maxLength={32}
              aria-invalid={errors.code ? true : undefined}
              className={INPUT}
            />
          </Field>
          <SelectField
            label="Topic"
            value={topic}
            onChange={(value) => value && setTopic(value as CompdTopic)}
            options={TOPIC_OPTIONS}
            placeholder="Choose a topic"
          />
        </>
      )}

      <fieldset className="flex flex-col gap-1">
        <legend className="text-sm font-bold text-ink-primary">Difficulty</legend>
        <div className="grid grid-cols-3 gap-2">
          {COMPD_DIFFICULTIES.map((d) => (
            <button
              key={d}
              type="button"
              aria-pressed={difficulty === d}
              onClick={() => setDifficulty(d)}
              className={`min-h-[44px] rounded-lg border text-sm font-bold ${
                difficulty === d
                  ? "border-watch-watching-border bg-watch-watching-bg text-watch-watching-fg"
                  : "border-border-strong bg-surface1 text-ink-secondary"
              }`}
            >
              {d}
            </button>
          ))}
        </div>
      </fieldset>

      <Field id={`${ids}-text`} label="Question" error={errors.text}>
        <textarea
          id={`${ids}-text`}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="e.g. 2 + 3 = ?"
          maxLength={500}
          rows={2}
          aria-invalid={errors.text ? true : undefined}
          className={`${INPUT} py-2`}
        />
      </Field>

      <Field id={`${ids}-answer`} label="Answer" error={errors.answer}>
        <input
          id={`${ids}-answer`}
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          placeholder="e.g. 5"
          maxLength={255}
          aria-invalid={errors.answer ? true : undefined}
          className={INPUT}
        />
      </Field>

      <Field id={`${ids}-options`} label="Options (comma-separated)" error={errors.options}>
        <input
          id={`${ids}-options`}
          value={optionsText}
          onChange={(e) => setOptionsText(e.target.value)}
          placeholder="Separate with commas, e.g. 4, 5, 6, 7"
          aria-invalid={errors.options ? true : undefined}
          className={INPUT}
        />
      </Field>

      {errors.form ? (
        <p role="alert" className="text-sm font-bold text-danger-text">
          {errors.form}
        </p>
      ) : null}

      <div className="grid grid-cols-2 gap-2">
        <button
          type="button"
          onClick={onDone}
          className="min-h-[44px] rounded-lg border border-border-strong text-sm font-bold text-ink-primary"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={save.isPending}
          className="min-h-[44px] rounded-lg bg-watch-watching-fg text-sm font-bold text-white disabled:opacity-60"
        >
          {save.isPending ? "Saving…" : editing ? "Save changes" : "Create question"}
        </button>
      </div>
    </form>
  );
}

function Field({
  id,
  label,
  error,
  children,
}: {
  id: string;
  label: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-bold text-ink-primary">
        {label}
      </label>
      {children}
      {error ? (
        <p role="alert" className="text-sm font-bold text-danger-text">
          {error}
        </p>
      ) : null}
    </div>
  );
}
