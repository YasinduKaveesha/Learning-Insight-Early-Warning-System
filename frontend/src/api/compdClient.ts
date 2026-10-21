// CompD's teacher side, served by THIS dashboard's own backend (owner direction
// 2026-10-21: "the teachers dashboard should be independent even with compD that
// is a must").
//
// WHERE THIS DATA LIVES. compD's children play inside the student app, so their
// answers and profiles are the student app's tables; Component 3's backend reads
// them read-only from the shared database, as it reads the class rosters. The
// question bank is Component 3's own table. So every call here goes to the
// dashboard API (VITE_API_BASE_URL, /api/v1/t3/compd/*) -- the same API and token
// httpClient.ts uses -- and never to the student app's API.
//
// ONE FILE, ON PURPOSE (plan 01 §1c). client.ts, httpClient.ts, mockClient.ts and
// lib/apiError.ts are not touched: the CompD section has its own types, its own
// errors and its own mock, so nothing here can change how the rest of the
// dashboard behaves.
//
// WHY CompdError HAS NO `code`. AuthorizationBoundary replaces the whole app with
// "your account is not authorized" the moment any cached error carries
// `code === "NOT_AUTHORIZED"`. That decision belongs to the dashboard's own
// requests; a failed CompD request stays a message on the CompD page. So
// CompdError never goes through lib/apiError.ts and carries a status only.

import { isSupabaseConfigured, supabase } from "./supabaseClient";
import * as mock from "./mock/fixtures/compd";

const BASE: string = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8100").replace(
  /\/$/,
  "",
);
const PREFIX = "/api/v1/t3/compd";

// --- Shapes (compD's names, contract v2.3) --------------------------------------

export type CompdLevel = "low" | "medium" | "high";
export type CompdSpeed = "Slow" | "Moderate" | "Fast";
export type CompdTopic = "Counting" | "Addition" | "Subtraction" | "Division";
export type CompdDifficulty = "Easy" | "Medium" | "Hard";

/** Q11 (D-028): the student app's four topics, in compD's form order. */
export const COMPD_TOPICS: readonly CompdTopic[] = ["Addition", "Subtraction", "Counting", "Division"];
export const COMPD_DIFFICULTIES: readonly CompdDifficulty[] = ["Easy", "Medium", "Hard"];

export interface CompdProfileFeatures {
  accuracy: number;
  avg_response_time_ms: number;
  retry_rate: number;
  hint_rate: number;
  total_questions: number;
}

/** One profile: the four levels, the recommendation and five activity statistics.
 * No confidence, score or model name -- the dashboard API never sends them, and
 * toProfile would drop them if it did. */
export interface CompdProfile {
  session_id: string;
  memory_level: CompdLevel;
  attention_level: CompdLevel;
  number_sense_level: CompdLevel;
  processing_speed_level: CompdSpeed;
  recommendation: string;
  features: CompdProfileFeatures;
  generated_at: string;
}

export interface CompdTopicPerformance {
  topic: string;
  total_questions: number;
  accuracy: number;
  avg_response_time_sec: number;
  retry_rate: number;
  hint_rate: number;
}

export interface CompdStudentPerformance {
  total_questions: number;
  completed_sessions: number;
  accuracy: number;
  avg_response_time_sec: number;
  avg_attempts: number;
  retry_rate: number;
  hint_rate: number;
  last_topic: string | null;
  topics: CompdTopicPerformance[];
}

export interface CompdStudentSummary {
  student_id: string;
  name: string | null;
  grade: string | null;
  classroom_name: string | null;
  total_interactions: number;
  latest_profile: CompdProfile | null;
  last_activity_date: string | null;
  performance: CompdStudentPerformance;
}

export interface CompdDashboardStats {
  total_students: number;
  students_with_profiles: number;
  total_interactions: number;
  average_accuracy: number;
  average_response_time_sec: number;
  needs_support_count: number;
}

export interface CompdDashboard {
  stats: CompdDashboardStats;
  students: CompdStudentSummary[];
}

export interface CompdStudentProfiles {
  student_id: string;
  name: string | null;
  classroom_name: string | null;
  /** Newest first: items[0] is the Profile section, items is the History. */
  items: CompdProfile[];
}

export interface CompdQuestion {
  id: string;
  question_code: string | null;
  topic: CompdTopic;
  difficulty: CompdDifficulty;
  question_text: string;
  correct_answer: string;
  options: string[] | null;
  created_at: string;
}

export interface CompdQuestionInput {
  question_code?: string | null;
  topic: CompdTopic;
  difficulty: CompdDifficulty;
  question_text: string;
  correct_answer: string;
  options?: string[] | null;
}

/** compD's edit form changes only these (EditQuestionsScreen.tsx:82-86). */
export type CompdQuestionPatch = Partial<
  Pick<CompdQuestionInput, "question_text" | "correct_answer" | "options" | "difficulty">
>;

export interface CompdQuestionFilter {
  topic?: CompdTopic;
  difficulty?: CompdDifficulty;
}

export interface CompdDraftRequest {
  topic: CompdTopic;
  difficulty: CompdDifficulty;
  count: number;
  instructions?: string;
}

export interface CompdApi {
  getDashboard(): Promise<CompdDashboard>;
  getStudentProfiles(studentId: string, limit: number): Promise<CompdStudentProfiles>;
  listQuestions(filter?: CompdQuestionFilter): Promise<CompdQuestion[]>;
  createQuestion(input: CompdQuestionInput): Promise<CompdQuestion>;
  updateQuestion(questionId: string, patch: CompdQuestionPatch): Promise<CompdQuestion>;
  deleteQuestion(questionId: string): Promise<void>;
  /** Drafts only -- nothing is saved until createQuestion is called for one. */
  draftQuestions(request: CompdDraftRequest): Promise<CompdQuestionInput[]>;
}

// --- Errors -----------------------------------------------------------------------

/** Every CompD failure. `status` is the HTTP status, or 0 when the request never
 * got an answer (the student app is down or unreachable). Deliberately no `code`
 * -- see the header. */
export class CompdError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "CompdError";
    this.status = status;
  }
}

/** Duck-typed, like lib/apiError's guards, so it matches across module boundaries. */
export function isCompdError(e: unknown): e is CompdError {
  return (
    typeof e === "object" &&
    e !== null &&
    (e as { name?: unknown }).name === "CompdError" &&
    typeof (e as { status?: unknown }).status === "number"
  );
}

/** TanStack `retry`: once, and only when the student app itself failed (5xx).
 * A 4xx is an answer, not an outage -- asking again cannot change it. */
export function compdRetry(failureCount: number, error: unknown): boolean {
  return isCompdError(error) && error.status >= 500 && failureCount < 1;
}

// --- Wire mapping -----------------------------------------------------------------

interface WireProfile extends CompdProfile {
  confidence_score?: unknown;
  model_version?: unknown;
}

function toProfile(p: WireProfile): CompdProfile {
  return {
    session_id: p.session_id,
    memory_level: p.memory_level,
    attention_level: p.attention_level,
    number_sense_level: p.number_sense_level,
    processing_speed_level: p.processing_speed_level,
    recommendation: p.recommendation,
    features: {
      accuracy: p.features.accuracy,
      avg_response_time_ms: p.features.avg_response_time_ms,
      retry_rate: p.features.retry_rate,
      hint_rate: p.features.hint_rate,
      total_questions: p.features.total_questions,
    },
    generated_at: p.generated_at,
  };
}

// --- HTTP -------------------------------------------------------------------------

async function headers(withBody: boolean): Promise<Record<string, string>> {
  const out: Record<string, string> = { Accept: "application/json" };
  if (withBody) out["Content-Type"] = "application/json";
  if (supabase) {
    const { data } = await supabase.auth.getSession();
    const token = data.session?.access_token;
    if (token) out.Authorization = `Bearer ${token}`;
  }
  return out;
}

async function request<T>(
  path: string,
  init: { method: "GET" | "POST"; body?: unknown } = { method: "GET" },
): Promise<T> {
  const hasBody = init.body !== undefined;
  let response: Response;
  try {
    response = await fetch(`${BASE}${PREFIX}${path}`, {
      method: init.method,
      headers: await headers(hasBody),
      body: hasBody ? JSON.stringify(init.body) : undefined,
    });
  } catch {
    throw new CompdError(0, `CompD request to ${path} got no response`);
  }
  if (!response.ok) {
    throw new CompdError(response.status, `CompD request to ${path} failed with HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

/** The real client. Exported so its request rules can be tested without a Supabase project. */
export const httpCompdApi: CompdApi = {
  async getDashboard() {
    const body = await request<{ stats: CompdDashboardStats; students: (CompdStudentSummary & { latest_profile: WireProfile | null })[] }>(
      "/dashboard",
    );
    return {
      stats: body.stats,
      students: body.students.map((s) => ({
        ...s,
        latest_profile: s.latest_profile ? toProfile(s.latest_profile) : null,
      })),
    };
  },

  async getStudentProfiles(studentId, limit) {
    const body = await request<CompdStudentProfiles & { items: WireProfile[] }>(
      `/students/${encodeURIComponent(studentId)}/profiles?limit=${limit}`,
    );
    return {
      student_id: body.student_id,
      name: body.name,
      classroom_name: body.classroom_name,
      items: body.items.map(toProfile),
    };
  },

  async listQuestions(filter = {}) {
    const query = new URLSearchParams({ limit: "100" });
    if (filter.topic) query.set("topic", filter.topic);
    if (filter.difficulty) query.set("difficulty", filter.difficulty);
    const body = await request<{ items: CompdQuestion[] }>(`/questions?${query.toString()}`);
    return body.items;
  },

  async createQuestion(input) {
    return request<CompdQuestion>("/questions", { method: "POST", body: input });
  },

  async updateQuestion(questionId, patch) {
    return request<CompdQuestion>(`/questions/${encodeURIComponent(questionId)}/update`, {
      method: "POST",
      body: patch,
    });
  },

  async deleteQuestion(questionId) {
    await request(`/questions/${encodeURIComponent(questionId)}/delete`, { method: "POST" });
  },

  async draftQuestions(draft) {
    const body = await request<{ drafts: CompdQuestionInput[] }>("/questions/drafts", {
      method: "POST",
      body: draft,
    });
    return body.drafts;
  },
};

/** The mock, for the same switch the rest of the dashboard uses (client.ts):
 * no Supabase project, or VITE_USE_MOCK=true, and every CompD page runs offline. */
export const mockCompdApi: CompdApi = {
  getDashboard: async () => mock.dashboard(),
  getStudentProfiles: async (studentId, limit) => mock.studentProfiles(studentId, limit),
  listQuestions: async (filter) => mock.listQuestions(filter),
  createQuestion: async (input) => mock.createQuestion(input),
  updateQuestion: async (questionId, patch) => mock.updateQuestion(questionId, patch),
  deleteQuestion: async (questionId) => mock.deleteQuestion(questionId),
  draftQuestions: async (draft) => mock.draftQuestions(draft),
};

export const compd: CompdApi = isSupabaseConfigured ? httpCompdApi : mockCompdApi;
