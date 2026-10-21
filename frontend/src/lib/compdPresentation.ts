// Every display rule of the CompD section, in one place (plan 03 §4).
//
// Ported from compD's own teacher screens, so the pages here show what compD
// showed: the needs-support rule and the focus area (TeacherDashboard.tsx:64-89),
// the options rule (ManualCreateScreen.tsx:53), the dimension blurbs and level
// bars (ProfileResultScreen.tsx), the history legend (ProfileHistoryScreen.tsx).
//
// ONE DELIBERATE CHANGE OF WORDS (owner Q3). compD said "low", "Needs Work",
// "Slow". A teacher reads "Needs practice" / "Developing" / "Strong" and
// "Takes time" / "Steady" / "Quick" instead. The rules are unchanged.
//
// No confidence, score, probability or model name is formatted here: those never
// reach the UI (lib/format.ts says the same of the rest of the dashboard).

import type {
  CompdDashboardStats,
  CompdLevel,
  CompdProfile,
  CompdSpeed,
  CompdStudentSummary,
} from "../api/compdClient";
import { isCompdError } from "../api/compdClient";

// --- Levels (owner Q3) -------------------------------------------------------------

export type CompdTone = "strong" | "developing" | "practice";

export function levelWord(level: CompdLevel | CompdSpeed): string {
  switch (level) {
    case "high":
      return "Strong";
    case "medium":
      return "Developing";
    case "low":
      return "Needs practice";
    case "Fast":
      return "Quick";
    case "Moderate":
      return "Steady";
    case "Slow":
      return "Takes time";
  }
}

export function levelTone(level: CompdLevel | CompdSpeed): CompdTone {
  if (level === "high" || level === "Fast") return "strong";
  if (level === "low" || level === "Slow") return "practice";
  return "developing";
}

/** Chip colours from the theme's tokens, never colour alone: the word is always shown. */
export const TONE_CHIP_CLASSES: Record<CompdTone, string> = {
  strong: "border-success bg-success-soft text-success-text",
  developing: "border-watch-watching-border bg-watch-watching-bg text-watch-watching-fg",
  practice: "border-statAmber-border bg-statAmber-bg text-statAmber-fg",
};

export const TONE_BAR_CLASSES: Record<CompdTone, string> = {
  strong: "bg-success",
  developing: "bg-accent-blue",
  practice: "bg-warning",
};

/** compD's level bar lengths (ProfileResultScreen.tsx levelBarWidth): 100% / 60% / 30%. */
export const TONE_BAR_WIDTH: Record<CompdTone, string> = {
  strong: "w-full",
  developing: "w-3/5",
  practice: "w-[30%]",
};

// --- The four dimensions (compD's titles and blurbs) ------------------------------

export type CompdDimension = "memory_level" | "attention_level" | "number_sense_level" | "processing_speed_level";

export const DIMENSIONS: readonly {
  key: CompdDimension;
  label: string;
  title: string;
  blurb: string;
}[] = [
  { key: "memory_level", label: "Memory", title: "Memory Performance", blurb: "How well you hold numbers and steps in mind." },
  { key: "attention_level", label: "Attention", title: "Attention Level", blurb: "How focused you stay while solving." },
  { key: "number_sense_level", label: "Number Sense", title: "Number Sense", blurb: "Your feel for how numbers work." },
  { key: "processing_speed_level", label: "Speed", title: "Processing Speed", blurb: "How quickly you answer confidently." },
];

/** compD's history legend (ProfileHistoryScreen.tsx:187-207), in the Q3 words. */
export const LEGEND: readonly { tone: CompdTone; words: string; meaning: string }[] = [
  { tone: "strong", words: "Strong / Quick", meaning: "Performing very well" },
  { tone: "developing", words: "Developing / Steady", meaning: "On track, keep going" },
  { tone: "practice", words: "Needs practice / Takes time", meaning: "Needs extra practice" },
];

// --- compD's teacher rules ---------------------------------------------------------

/** compD TeacherDashboard.tsx:64-74 (the same rule the dashboard API counts in
 * `needs_support_count`): a level to practise or Slow speed on the latest
 * profile, or at least 5 questions under 60% accuracy. */
export function needsSupport(student: CompdStudentSummary): boolean {
  const p = student.latest_profile;
  const perf = student.performance;
  return (
    p?.memory_level === "low" ||
    p?.attention_level === "low" ||
    p?.number_sense_level === "low" ||
    p?.processing_speed_level === "Slow" ||
    (perf.total_questions >= 5 && perf.accuracy < 0.6)
  );
}

/** compD TeacherDashboard.tsx:76-89: "No profile", "None", or the weak areas joined with ", ". */
export function weakestArea(profile: CompdProfile | null): string {
  if (!profile) return "No profile";
  const weak = DIMENSIONS.filter((d) => {
    const level = profile[d.key];
    return level === "low" || level === "Slow";
  });
  return weak.length ? weak.map((d) => d.label).join(", ") : "None";
}

export type StudentFilter = "support" | "missing" | "all";

/** compD's three task buttons, with their labels, in compD's order. */
export const STUDENT_FILTERS: readonly { value: StudentFilter; label: string }[] = [
  { value: "support", label: "Review support" },
  { value: "missing", label: "Missing profiles" },
  { value: "all", label: "All students" },
];

/** compD's filter, plus the name search added here (the list spans every class). */
export function filterStudents(
  students: CompdStudentSummary[],
  filter: StudentFilter,
  search = "",
): CompdStudentSummary[] {
  const needle = search.trim().toLowerCase();
  return students.filter((s) => {
    if (filter === "support" && !needsSupport(s)) return false;
    if (filter === "missing" && s.latest_profile) return false;
    if (needle && !(s.name ?? "").toLowerCase().includes(needle)) return false;
    return true;
  });
}

/** compD showed the name, then the code or a slice of the id; the code is gone (contract v2.3). */
export function studentName(name: string | null): string {
  return name?.trim() || "Unnamed student";
}

/** Added, not compD: the class and grade on the card. */
export function classLine(classroomName: string | null, grade: string | null): string {
  const room = classroomName?.trim() || "No class";
  return grade ? `${room} · Grade ${grade}` : room;
}

// --- The options rule (contract v2.3) ----------------------------------------------

export const MIN_OPTIONS = 2;
export const MAX_OPTIONS = 6;

/** compD's comma-separated options field: "4, 5, 6" → ["4", "5", "6"]. */
export function parseOptions(text: string): string[] {
  return text
    .split(",")
    .map((o) => o.trim())
    .filter(Boolean);
}

export type OptionsResult = { ok: true; options: string[] | null } | { ok: false; error: string };

/** As compD's form did (ManualCreateScreen.tsx:53), the answer is appended when
 * the options leave it out; then 2-6 options. Differs from compD in one case:
 * a question whose only option was its answer saved in compD; here it asks for
 * another option, because the dashboard API refuses it. No options at all is
 * allowed, as in compD. */
export function withAnswer(options: string[], answer: string): OptionsResult {
  if (options.length === 0) return { ok: true, options: null };
  const result = options.includes(answer) ? [...options] : [...options, answer];
  if (result.length < MIN_OPTIONS) return { ok: false, error: "Add at least one other option" };
  if (result.length > MAX_OPTIONS) {
    return { ok: false, error: `Use at most ${MAX_OPTIONS} options, including the answer` };
  }
  return { ok: true, options: result };
}

// --- Numbers and dates -------------------------------------------------------------

/** compD's pct: a share as a whole percentage. Accuracy and hint use are
 * activity data (what the child did), not a model's confidence. */
export function pct(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export function seconds(value: number): string {
  return `${value.toFixed(1)}s`;
}

export function avgTimeLabel(stats: CompdDashboardStats): string {
  return `Avg time ${seconds(stats.average_response_time_sec)}`;
}

export function shownOf(shown: number, total: number): string {
  return `${shown} shown of ${total}`;
}

export function basedOn(totalQuestions: number, accuracy: number): string {
  const noun = totalQuestions === 1 ? "question" : "questions";
  return `Based on ${totalQuestions} ${noun} · ${pct(accuracy)} correctness`;
}

export function profilesRecorded(count: number): string {
  return `${count} profile${count === 1 ? "" : "s"} recorded`;
}

export function questionCount(count: number): string {
  return `${count} question${count === 1 ? "" : "s"} in bank`;
}

/** compD's history card date: "21/10/2026 – 09:30", in the browser's locale. */
export function dateAndTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const day = date.toLocaleDateString();
  const time = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return `${day} – ${time}`;
}

/** compD's "Last activity: …" line. */
export function lastActivity(iso: string | null): string {
  if (!iso) return "Last activity: No activity";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "Last activity: No activity";
  return `Last activity: ${date.toLocaleDateString()}`;
}

// --- Messages (plan 03 §4) ---------------------------------------------------------

export const LOAD_FAILED = "Couldn't load this. Check your connection and try again.";
export const NOT_AVAILABLE = "This item isn't available.";
export const AI_UNAVAILABLE =
  "AI generation isn't available right now. You can still create questions by hand.";
export const AI_UNUSABLE = "The AI didn't return any usable questions. Please try again.";
export const DUPLICATE_CODE = "A question with that code already exists.";
export const SAVE_FAILED = "Couldn't save. Check your connection and try again.";

/** What a failed CompD request says on the page. Never the raw error. */
export function loadErrorMessage(error: unknown): string {
  if (isCompdError(error) && error.status === 404) return NOT_AVAILABLE;
  return LOAD_FAILED;
}
