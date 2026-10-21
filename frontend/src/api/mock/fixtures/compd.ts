// Mock data for the CompD section (plan 03 §4), used whenever the rest of the
// dashboard runs on MockClient: no Supabase project, or VITE_USE_MOCK=true.
//
// THE CHILDREN are the mock roster's own (ROSTER_SNAPSHOTS): their ids and display
// names, and the class each sits in. Their CompD activity is AUTHORED here --
// deterministic from each child's position, so a page looks the same on every
// load -- and is not derived from their watch-list data, exactly as the real
// CompD section and the watch list are separate sources (plan 01 §1b).
//
// THE QUESTION BANK lives in memory for the session, like the mock's created
// classes: a reload starts it again. It applies the same options rule and the
// same unique-code rule as the dashboard API, so the forms behave as they will live.
//
// AI DRAFTS are fixed samples built from the request, never a network call.

import type {
  CompdDashboard,
  CompdDashboardStats,
  CompdDifficulty,
  CompdDraftRequest,
  CompdLevel,
  CompdProfile,
  CompdQuestion,
  CompdQuestionFilter,
  CompdQuestionInput,
  CompdQuestionPatch,
  CompdSpeed,
  CompdStudentPerformance,
  CompdStudentProfiles,
  CompdStudentSummary,
  CompdTopic,
} from "../../compdClient";
import { CompdError } from "../../compdClient";
import { needsSupport, withAnswer } from "../../../lib/compdPresentation";
import { allClasses, ROSTER_SNAPSHOTS } from "./authored";

const LEVELS: CompdLevel[] = ["high", "medium", "low", "medium"];
const SPEEDS: CompdSpeed[] = ["Moderate", "Fast", "Slow", "Moderate"];
const TOPICS: CompdTopic[] = ["Addition", "Subtraction", "Counting", "Division"];
const ACCURACY = [0.9, 0.75, 0.5, 0.8, 0.65];
const RECOMMENDATION =
  "Keep practising short sets of questions, and praise steady effort as well as correct answers.";

// Every fifth child has not played yet, so "Missing profiles" is never empty.
function playedCount(index: number): number {
  return index % 5 === 4 ? 0 : 1 + (index % 3);
}

function profileFor(index: number, run: number, accuracy: number): CompdProfile {
  const generated = new Date(Date.UTC(2026, 9, 20 - run, 9, 30));
  return {
    session_id: `mock-run-${index}-${run}`,
    memory_level: LEVELS[(index + run) % LEVELS.length]!,
    attention_level: LEVELS[(index + run + 1) % LEVELS.length]!,
    number_sense_level: LEVELS[(index + 2 * run + 3) % LEVELS.length]!,
    processing_speed_level: SPEEDS[(index + run) % SPEEDS.length]!,
    recommendation: RECOMMENDATION,
    features: {
      accuracy,
      avg_response_time_ms: 2800 + 400 * (index % 4),
      retry_rate: 0.1 * (index % 3),
      hint_rate: 0.1 * (index % 2),
      total_questions: 10,
    },
    generated_at: generated.toISOString(),
  };
}

function performanceFor(index: number, runs: number, accuracy: number): CompdStudentPerformance {
  if (runs === 0) {
    return {
      total_questions: 0,
      completed_sessions: 0,
      accuracy: 0,
      avg_response_time_sec: 0,
      avg_attempts: 1,
      retry_rate: 0,
      hint_rate: 0,
      last_topic: null,
      topics: [],
    };
  }
  const total = 10 * runs;
  const topics = TOPICS.slice(0, 1 + (index % 4)).map((topic, t) => ({
    topic,
    total_questions: Math.max(1, Math.round(total / (t + 2))),
    accuracy: Math.min(1, accuracy + 0.05 * t),
    avg_response_time_sec: 3 + 0.4 * t,
    retry_rate: 0.1,
    hint_rate: 0.1 * (t % 2),
  }));
  return {
    total_questions: total,
    completed_sessions: runs,
    accuracy,
    avg_response_time_sec: 2.8 + 0.4 * (index % 4),
    avg_attempts: 1.2,
    retry_rate: 0.1 * (index % 3),
    hint_rate: 0.1 * (index % 2),
    last_topic: topics[topics.length - 1]!.topic,
    topics: [...topics].sort((a, b) => b.total_questions - a.total_questions),
  };
}

interface MockChild {
  summary: CompdStudentSummary;
  history: CompdProfile[];
}

function buildChildren(): MockChild[] {
  const classNames = new Map(allClasses().map((c) => [c.classId, c.name]));
  return ROSTER_SNAPSHOTS.map((snapshot, index) => {
    const runs = playedCount(index);
    const accuracy = ACCURACY[index % ACCURACY.length]!;
    const history = Array.from({ length: runs }, (_, run) => profileFor(index, run, accuracy));
    const summary: CompdStudentSummary = {
      student_id: snapshot.studentId,
      name: snapshot.displayName,
      grade: snapshot.classId.startsWith("class-2") ? "2" : "3",
      classroom_name: classNames.get(snapshot.classId) ?? null,
      total_interactions: 10 * runs,
      latest_profile: history[0] ?? null,
      last_activity_date: history[0]?.generated_at ?? null,
      performance: performanceFor(index, runs, accuracy),
    };
    return { summary, history };
  }).sort((a, b) => (a.summary.name ?? "").localeCompare(b.summary.name ?? ""));
}

/** compD teacher.py:195-222, as the dashboard API computes it. */
function statsFor(students: CompdStudentSummary[]): CompdDashboardStats {
  const totalQuestions = students.reduce((sum, s) => sum + s.performance.total_questions, 0);
  const weighted = (pick: (s: CompdStudentSummary) => number) =>
    totalQuestions
      ? students.reduce((sum, s) => sum + pick(s) * s.performance.total_questions, 0) / totalQuestions
      : 0;
  return {
    total_students: students.length,
    students_with_profiles: students.filter((s) => s.latest_profile).length,
    total_interactions: students.reduce((sum, s) => sum + s.total_interactions, 0),
    average_accuracy: Math.round(weighted((s) => s.performance.accuracy) * 100) / 100,
    average_response_time_sec: Math.round(weighted((s) => s.performance.avg_response_time_sec) * 10) / 10,
    needs_support_count: students.filter(needsSupport).length,
  };
}

const CHILDREN = buildChildren();

export function dashboard(): CompdDashboard {
  const students = CHILDREN.map((c) => c.summary);
  return { stats: statsFor(students), students };
}

export function studentProfiles(studentId: string, limit: number): CompdStudentProfiles {
  const child = CHILDREN.find((c) => c.summary.student_id === studentId);
  if (!child) throw new CompdError(404, `No mock CompD learner ${studentId}`);
  return {
    student_id: studentId,
    name: child.summary.name,
    classroom_name: child.summary.classroom_name,
    items: child.history.slice(0, limit),
  };
}

// --- The question bank, in memory for this session ---------------------------------

let nextId = 1;
let bank: CompdQuestion[] = [];

function stamp(): string {
  return new Date(Date.UTC(2026, 9, 21, 8, 0, nextId)).toISOString();
}

function codeTaken(code: string | null | undefined, exceptId?: string): boolean {
  return Boolean(code) && bank.some((q) => q.question_code === code && q.id !== exceptId);
}

function checkedOptions(options: string[] | null | undefined, answer: string): string[] | null {
  const result = withAnswer(options ?? [], answer);
  if (!result.ok) throw new CompdError(422, result.error);
  return result.options;
}

export function listQuestions(filter: CompdQuestionFilter = {}): CompdQuestion[] {
  return bank
    .filter((q) => !filter.topic || q.topic === filter.topic)
    .filter((q) => !filter.difficulty || q.difficulty === filter.difficulty)
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .slice(0, 100);
}

export function createQuestion(input: CompdQuestionInput): CompdQuestion {
  if (codeTaken(input.question_code)) throw new CompdError(409, "Duplicate question code");
  const question: CompdQuestion = {
    id: `mock-question-${nextId}`,
    question_code: input.question_code || null,
    topic: input.topic,
    difficulty: input.difficulty,
    question_text: input.question_text,
    correct_answer: input.correct_answer,
    options: checkedOptions(input.options, input.correct_answer),
    created_at: stamp(),
  };
  nextId += 1;
  bank = [question, ...bank];
  return question;
}

export function updateQuestion(questionId: string, patch: CompdQuestionPatch): CompdQuestion {
  const current = bank.find((q) => q.id === questionId);
  if (!current) throw new CompdError(404, `No mock question ${questionId}`);
  const answer = patch.correct_answer ?? current.correct_answer;
  const updated: CompdQuestion = {
    ...current,
    ...patch,
    correct_answer: answer,
    options:
      patch.options !== undefined || patch.correct_answer !== undefined
        ? checkedOptions(patch.options !== undefined ? patch.options : current.options, answer)
        : current.options,
  };
  bank = bank.map((q) => (q.id === questionId ? updated : q));
  return updated;
}

export function deleteQuestion(questionId: string): void {
  if (!bank.some((q) => q.id === questionId)) throw new CompdError(404, `No mock question ${questionId}`);
  bank = bank.filter((q) => q.id !== questionId);
}

/** Tests start each case from an empty bank. */
export function resetQuestionBank(): void {
  bank = [];
  nextId = 1;
}

// --- AI drafts: fixed samples, topic and difficulty as requested --------------------

const SIZE: Record<CompdDifficulty, number> = { Easy: 5, Medium: 12, Hard: 25 };

function sample(topic: CompdTopic, difficulty: CompdDifficulty, n: number): CompdQuestionInput {
  const a = SIZE[difficulty] + n;
  const b = 1 + (n % 4);
  const [text, answer]: [string, number] =
    topic === "Addition"
      ? [`${a} + ${b} = ?`, a + b]
      : topic === "Subtraction"
        ? [`${a} - ${b} = ?`, a - b]
        : topic === "Division"
          ? [`${a * b} ÷ ${b} = ?`, a]
          : [`What number comes after ${a}?`, a + 1];
  return {
    topic,
    difficulty,
    question_text: text,
    correct_answer: String(answer),
    options: [String(answer - 1), String(answer), String(answer + 1), String(answer + 2)],
  };
}

export function draftQuestions(request: CompdDraftRequest): CompdQuestionInput[] {
  return Array.from({ length: request.count }, (_, n) => sample(request.topic, request.difficulty, n));
}
