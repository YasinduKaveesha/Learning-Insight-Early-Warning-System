import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// A configured Supabase project with a signed-in teacher, so the REAL client is chosen.
vi.mock("../../../api/supabaseClient", () => ({
  isSupabaseConfigured: true,
  supabase: {
    auth: {
      getSession: async () => ({ data: { session: { access_token: "teacher-token" } } }),
    },
  },
}));

const { CompdError, compd, compdRetry, httpCompdApi, isCompdError } = await import("../../../api/compdClient");
const { isNotAuthorizedError } = await import("../../../lib/apiError");

interface Call {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: unknown;
}

let calls: Call[] = [];

// The same base the client reads (the dashboard's .env may set it), so the test
// checks the path and query, not one machine's host.
const BASE = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8100").replace(/\/$/, "");

function respond(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit) => {
      calls.push({
        url,
        method: init.method ?? "GET",
        headers: init.headers as Record<string, string>,
        body: init.body ? JSON.parse(init.body as string) : undefined,
      });
      return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
    }),
  );
}

const WIRE_QUESTION = {
  id: "q-1",
  question_code: "ADD-1",
  topic: "Addition",
  difficulty: "Easy",
  question_text: "2 + 3 = ?",
  correct_answer: "5",
  options: ["4", "5"],
  created_at: "2026-10-21T08:00:00Z",
};

const WIRE_PROFILE = {
  session_id: "run-1",
  memory_level: "high",
  attention_level: "medium",
  number_sense_level: "low",
  processing_speed_level: "Fast",
  confidence_score: 0.73,
  recommendation: "Keep going.",
  model_version: "rule-based-v2",
  features: {
    accuracy: 0.8, avg_response_time_ms: 3000, response_time_std_ms: 10, avg_attempts: 1.1,
    retry_rate: 0.1, hint_rate: 0.2, mean_clicks_per_question: 1.5, total_questions: 10,
  },
  generated_at: "2026-10-20T09:30:00Z",
  request_id: "req-ignored",
};

beforeEach(() => {
  calls = [];
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("compdClient (U9)", () => {
  it("uses the real client when a Supabase project is configured", () => {
    expect(compd).toBe(httpCompdApi);
  });

  it("calls the DASHBOARD's own API with the teacher's Bearer token -- never the student app's", async () => {
    respond(200, { stats: {}, students: [], request_id: "r" });
    await httpCompdApi.getDashboard();
    expect(calls[0]!.url).toBe(`${BASE}/api/v1/t3/compd/dashboard`);
    expect(calls[0]!.url).not.toContain(":8000");
    expect(calls[0]!.method).toBe("GET");
    expect(calls[0]!.headers.Authorization).toBe("Bearer teacher-token");

    respond(200, { student_id: "s-1", name: "A", classroom_name: null, items: [WIRE_PROFILE], request_id: "r" });
    const profiles = await httpCompdApi.getStudentProfiles("s-1", 20);
    expect(calls[1]!.url).toBe(`${BASE}/api/v1/t3/compd/students/s-1/profiles?limit=20`);
    // A confidence value and the model version never leave the client.
    expect(Object.keys(profiles.items[0]!)).not.toContain("confidence_score");
    expect(Object.keys(profiles.items[0]!)).not.toContain("model_version");
    expect(JSON.stringify(profiles)).not.toMatch(/confidence|rule-based/);
  });

  it("uses only GET and POST; update and delete are POSTs", async () => {
    respond(200, { items: [WIRE_QUESTION], request_id: "r" });
    await httpCompdApi.listQuestions({ topic: "Addition" });
    respond(200, WIRE_QUESTION);
    await httpCompdApi.updateQuestion("q-1", { question_text: "x" });
    respond(200, { message: "Question deleted", id: "q-1", request_id: "r" });
    await httpCompdApi.deleteQuestion("q-1");

    expect(calls.map((c) => c.method)).toEqual(["GET", "POST", "POST"]);
    expect(calls[0]!.url).toBe(`${BASE}/api/v1/t3/compd/questions?limit=100&topic=Addition`);
    expect(calls[1]!.url).toBe(`${BASE}/api/v1/t3/compd/questions/q-1/update`);
    expect(calls[2]!.url).toBe(`${BASE}/api/v1/t3/compd/questions/q-1/delete`);
  });

  it("sends and reads compD's own field names, correct_answer included", async () => {
    respond(201, WIRE_QUESTION);
    const created = await httpCompdApi.createQuestion({
      topic: "Addition",
      difficulty: "Easy",
      question_text: "2 + 3 = ?",
      correct_answer: "5",
      options: ["4", "5"],
    });
    expect(calls[0]!.body).toEqual({
      topic: "Addition", difficulty: "Easy", question_text: "2 + 3 = ?", correct_answer: "5", options: ["4", "5"],
    });
    expect(created.correct_answer).toBe("5");

    respond(200, WIRE_QUESTION);
    await httpCompdApi.updateQuestion("q-1", { correct_answer: "6" });
    expect(calls[1]!.body).toEqual({ correct_answer: "6" });

    respond(200, { drafts: [{ topic: "Addition", difficulty: "Easy", question_text: "1 + 1 = ?", correct_answer: "2", options: ["1", "2"] }] });
    const drafts = await httpCompdApi.draftQuestions({ topic: "Addition", difficulty: "Easy", count: 1 });
    expect(drafts[0]!.correct_answer).toBe("2");
  });

  it("a 403 throws a CompdError that the account lock-out can never match", async () => {
    respond(403, { error: { code: "FORBIDDEN" } });
    const error = await httpCompdApi.getDashboard().catch((e: unknown) => e);
    expect(isCompdError(error)).toBe(true);
    expect((error as InstanceType<typeof CompdError>).status).toBe(403);
    expect(error).not.toHaveProperty("code");
    expect(isNotAuthorizedError(error)).toBe(false);
  });

  it("no answer at all is a CompdError with status 0", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));
    const error = await httpCompdApi.listQuestions().catch((e: unknown) => e);
    expect(isCompdError(error)).toBe(true);
    expect((error as InstanceType<typeof CompdError>).status).toBe(0);
  });

  it("retries once on a 5xx and never on a 4xx", () => {
    expect(compdRetry(0, new CompdError(500, "x"))).toBe(true);
    expect(compdRetry(0, new CompdError(503, "x"))).toBe(true);
    expect(compdRetry(1, new CompdError(500, "x"))).toBe(false);
    for (const status of [0, 403, 404, 409, 422]) {
      expect(compdRetry(0, new CompdError(status, "x"))).toBe(false);
    }
    expect(compdRetry(0, new Error("not ours"))).toBe(false);
  });
});
