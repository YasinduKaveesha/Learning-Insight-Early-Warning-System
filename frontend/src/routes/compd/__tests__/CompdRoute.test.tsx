import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import App from "../../../App";
import {
  CompdError,
  compd,
  mockCompdApi,
  type CompdDashboard,
  type CompdProfile,
  type CompdStudentSummary,
} from "../../../api/compdClient";
import { createQuestion, resetQuestionBank } from "../../../api/mock/fixtures/compd";
import CompdRoute from "../CompdRoute";

function Probe() {
  const location = useLocation();
  return <div data-testid="location">{`${location.pathname}${location.search}${location.hash}`}</div>;
}

function renderCompd(path = "/compd") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/compd" element={<CompdRoute />} />
          <Route path="/compd/students/:studentId" element={<div>Student page</div>} />
        </Routes>
        <Probe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function profile(overrides: Partial<CompdProfile> = {}): CompdProfile {
  return {
    session_id: "run-1",
    memory_level: "medium",
    attention_level: "medium",
    number_sense_level: "medium",
    processing_speed_level: "Moderate",
    recommendation: "Keep practising.",
    features: { accuracy: 0.8, avg_response_time_ms: 3000, retry_rate: 0.1, hint_rate: 0.2, total_questions: 10 },
    generated_at: "2026-10-20T09:30:00Z",
    ...overrides,
  };
}

function student(overrides: Partial<CompdStudentSummary>): CompdStudentSummary {
  return {
    student_id: "s-0",
    name: "Child",
    grade: "2",
    classroom_name: "Grade 2 Gold",
    total_interactions: 10,
    latest_profile: profile(),
    last_activity_date: "2026-10-20T09:30:00Z",
    performance: {
      total_questions: 10,
      completed_sessions: 1,
      accuracy: 0.8,
      avg_response_time_sec: 3,
      avg_attempts: 1.2,
      retry_rate: 0.1,
      hint_rate: 0.2,
      last_topic: "Addition",
      topics: [
        { topic: "Addition", total_questions: 6, accuracy: 0.83, avg_response_time_sec: 3, retry_rate: 0, hint_rate: 0 },
        { topic: "Counting", total_questions: 3, accuracy: 0.67, avg_response_time_sec: 3, retry_rate: 0, hint_rate: 0 },
        { topic: "Division", total_questions: 1, accuracy: 1, avg_response_time_sec: 3, retry_rate: 0, hint_rate: 0 },
        { topic: "Subtraction", total_questions: 1, accuracy: 1, avg_response_time_sec: 3, retry_rate: 0, hint_rate: 0 },
      ],
    },
    ...overrides,
  };
}

const DASHBOARD: CompdDashboard = {
  stats: {
    total_students: 3,
    students_with_profiles: 2,
    total_interactions: 20,
    average_accuracy: 0.65,
    average_response_time_sec: 3.4,
    needs_support_count: 1,
  },
  students: [
    student({ student_id: "s-amal", name: "Amal" }),
    student({
      student_id: "s-bimal",
      name: "Bimal",
      classroom_name: null,
      latest_profile: profile({ memory_level: "low", processing_speed_level: "Slow" }),
    }),
    student({
      student_id: "s-chamal",
      name: "Chamal",
      grade: null,
      latest_profile: null,
      total_interactions: 0,
      last_activity_date: null,
      performance: {
        total_questions: 0, completed_sessions: 0, accuracy: 0, avg_response_time_sec: 0,
        avg_attempts: 1, retry_rate: 0, hint_rate: 0, last_topic: null, topics: [],
      },
    }),
  ],
};

beforeEach(() => {
  resetQuestionBank();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("CompD — the mock switch", () => {
  it("runs on the mock with no Supabase project, like the rest of the dashboard", () => {
    expect(compd).toBe(mockCompdApi);
  });
});

describe("/compd — the two tabs (U2)", () => {
  it("shows compD's two titles, with Students first and selected", async () => {
    renderCompd();
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual(["Students Dashboard", "Practice Questions"]);
    expect(screen.getByRole("tab", { name: "Students Dashboard" })).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByText("Avg accuracy")).toBeInTheDocument();
  });

  it("?tab=questions opens Questions, and switching writes the tab into the URL", async () => {
    const user = userEvent.setup();
    renderCompd("/compd?tab=questions");
    expect(screen.getByRole("tab", { name: "Practice Questions" })).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByRole("button", { name: "Create manually" })).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Students Dashboard" }));
    expect(screen.getByTestId("location")).toHaveTextContent("/compd?tab=students");
    await user.click(screen.getByRole("tab", { name: "Practice Questions" }));
    expect(screen.getByTestId("location")).toHaveTextContent("/compd?tab=questions");
  });

  it("has a back link to Home", () => {
    renderCompd();
    expect(screen.getByRole("link", { name: "Back to Home" })).toHaveAttribute("href", "/");
  });
});

describe("Students tab (U3)", () => {
  beforeEach(() => {
    vi.spyOn(compd, "getDashboard").mockResolvedValue(DASHBOARD);
  });

  it("shows compD's four tiles, the list header and every child", async () => {
    renderCompd();
    expect(await screen.findByText("Avg accuracy")).toBeInTheDocument();
    expect(screen.getByText("65%")).toBeInTheDocument();
    expect(screen.getByText("Need support")).toBeInTheDocument();
    expect(screen.getByText("Avg time 3.4s")).toBeInTheDocument();
    expect(screen.getByText("3 shown of 3")).toBeInTheDocument();
    expect(screen.getAllByRole("article").map((a) => a.getAttribute("aria-label"))).toEqual([
      "Amal",
      "Bimal",
      "Chamal",
    ]);
  });

  it("each card carries compD's badge, metrics, chips, focus area, topics and actions -- and the class", async () => {
    renderCompd();
    const amal = await screen.findByRole("article", { name: "Amal" });
    const a = within(amal);
    expect(a.getByText("On track")).toBeInTheDocument();
    expect(a.getByText("Grade 2 Gold · Grade 2")).toBeInTheDocument();
    for (const label of ["Questions", "Sessions", "Avg time", "Hints"]) expect(a.getByText(label)).toBeInTheDocument();
    expect(a.getAllByText("Developing")).toHaveLength(3);
    expect(a.getByText("Steady")).toBeInTheDocument();
    expect(a.getByText("None")).toBeInTheDocument();
    // The top three topics only.
    expect(a.getByText("Addition 83%")).toBeInTheDocument();
    expect(a.getByText("Division 100%")).toBeInTheDocument();
    expect(a.queryByText("Subtraction 100%")).not.toBeInTheDocument();
    expect(a.getByRole("link", { name: "View profile" })).toHaveAttribute("href", "/compd/students/s-amal");
    expect(a.getByRole("link", { name: "History" })).toHaveAttribute("href", "/compd/students/s-amal#history");

    const bimal = within(screen.getByRole("article", { name: "Bimal" }));
    expect(bimal.getByText("Support")).toBeInTheDocument();
    expect(bimal.getByText("No class · Grade 2")).toBeInTheDocument();
    expect(bimal.getByText("Memory, Speed")).toBeInTheDocument();
    expect(bimal.getByText("Needs practice")).toBeInTheDocument();
    expect(bimal.getByText("Takes time")).toBeInTheDocument();

    const chamal = within(screen.getByRole("article", { name: "Chamal" }));
    expect(chamal.getByText("No profile")).toBeInTheDocument();
    expect(chamal.getByText("No profile generated yet")).toBeInTheDocument();
    expect(chamal.getByText("Last activity: No activity")).toBeInTheDocument();
  });

  it("the three filters and the search narrow the list", async () => {
    const user = userEvent.setup();
    renderCompd();
    await screen.findByRole("article", { name: "Amal" });

    await user.click(screen.getByRole("button", { name: "Review support" }));
    expect(screen.getAllByRole("article").map((a) => a.getAttribute("aria-label"))).toEqual(["Bimal"]);
    expect(screen.getByText("1 shown of 3")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Missing profiles" }));
    expect(screen.getAllByRole("article").map((a) => a.getAttribute("aria-label"))).toEqual(["Chamal"]);

    await user.click(screen.getByRole("button", { name: "All students" }));
    await user.type(screen.getByRole("searchbox", { name: "Search students" }), "BIM");
    expect(screen.getAllByRole("article").map((a) => a.getAttribute("aria-label"))).toEqual(["Bimal"]);
  });
});

describe("Questions tab (U6)", () => {
  it("an empty bank offers Create manually and Generate with AI", async () => {
    renderCompd("/compd?tab=questions");
    expect(await screen.findByText("No questions yet. Create one, or generate some with AI.")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Create manually" })).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "Generate with AI" })).toHaveLength(2);
  });

  it("lists the bank with code, topic, difficulty, text, answer and options; filters by topic", async () => {
    const user = userEvent.setup();
    createQuestion({ question_code: "ADD-1", topic: "Addition", difficulty: "Easy", question_text: "2 + 3 = ?", correct_answer: "5", options: ["4", "5"] });
    createQuestion({ topic: "Division", difficulty: "Hard", question_text: "8 ÷ 2 = ?", correct_answer: "4", options: null });
    renderCompd("/compd?tab=questions");

    expect(await screen.findByText("2 + 3 = ?")).toBeInTheDocument();
    expect(screen.getByText("2 questions in bank")).toBeInTheDocument();
    expect(screen.getByText("ADD-1")).toBeInTheDocument();
    expect(screen.getByText("Answer: 5")).toBeInTheDocument();
    expect(screen.getByText("Options: 4, 5")).toBeInTheDocument();

    await user.click(screen.getByRole("combobox", { name: /^Topic/ }));
    await user.click(screen.getByRole("option", { name: "Division" }));
    await waitFor(() => expect(screen.queryByText("2 + 3 = ?")).not.toBeInTheDocument());
    expect(screen.getByText("8 ÷ 2 = ?")).toBeInTheDocument();
    expect(screen.getByText("1 shown")).toBeInTheDocument();
  });

  it("Delete asks first, then the list refreshes without the question", async () => {
    const user = userEvent.setup();
    createQuestion({ topic: "Addition", difficulty: "Easy", question_text: "1 + 1 = ?", correct_answer: "2", options: null });
    renderCompd("/compd?tab=questions");

    await user.click(await screen.findByRole("button", { name: 'Delete "1 + 1 = ?"' }));
    const dialog = screen.getByRole("dialog", { name: "Delete question" });
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.getByText("1 + 1 = ?")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: 'Delete "1 + 1 = ?"' }));
    await user.click(within(screen.getByRole("dialog", { name: "Delete question" })).getByRole("button", { name: "Delete" }));
    expect(await screen.findByText("No questions yet. Create one, or generate some with AI.")).toBeInTheDocument();
  });
});

describe("QuestionForm (U7)", () => {
  async function openCreate() {
    const user = userEvent.setup();
    renderCompd("/compd?tab=questions");
    await user.click((await screen.findAllByRole("button", { name: "Create manually" }))[0]!);
    return { user, dialog: screen.getByRole("dialog", { name: "Create a question" }) };
  }

  it("appends the answer to the options, saves, closes and refreshes the list", async () => {
    const { user, dialog } = await openCreate();
    const d = within(dialog);
    await user.type(d.getByLabelText("Question"), "2 + 3 = ?");
    await user.type(d.getByLabelText("Answer"), "5");
    await user.type(d.getByLabelText("Options (comma-separated)"), "4, 6");
    await user.click(d.getByRole("button", { name: "Create question" }));

    expect(await screen.findByText("Options: 4, 6, 5")).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Create a question" })).not.toBeInTheDocument();
  });

  it("only the answer asks for another option; more than six is refused", async () => {
    const { user, dialog } = await openCreate();
    const d = within(dialog);
    await user.type(d.getByLabelText("Question"), "2 + 3 = ?");
    await user.type(d.getByLabelText("Answer"), "5");
    await user.type(d.getByLabelText("Options (comma-separated)"), "5");
    await user.click(d.getByRole("button", { name: "Create question" }));
    expect(d.getByText("Add at least one other option")).toBeInTheDocument();

    await user.clear(d.getByLabelText("Options (comma-separated)"));
    await user.type(d.getByLabelText("Options (comma-separated)"), "1, 2, 3, 4, 6, 7");
    await user.click(d.getByRole("button", { name: "Create question" }));
    expect(d.getByText("Use at most 6 options, including the answer")).toBeInTheDocument();
  });

  it("a duplicate code is refused on the code field", async () => {
    vi.spyOn(compd, "createQuestion").mockRejectedValue(new CompdError(409, "conflict"));
    const { user, dialog } = await openCreate();
    const d = within(dialog);
    await user.type(d.getByLabelText("Question code"), "ADD-021");
    await user.type(d.getByLabelText("Question"), "2 + 3 = ?");
    await user.type(d.getByLabelText("Answer"), "5");
    await user.click(d.getByRole("button", { name: "Create question" }));
    expect(await d.findByText("A question with that code already exists.")).toBeInTheDocument();
  });

  it("Save is disabled while the save is in flight", async () => {
    vi.spyOn(compd, "createQuestion").mockReturnValue(new Promise(() => {}));
    const { user, dialog } = await openCreate();
    const d = within(dialog);
    await user.type(d.getByLabelText("Question"), "2 + 3 = ?");
    await user.type(d.getByLabelText("Answer"), "5");
    await user.click(d.getByRole("button", { name: "Create question" }));
    expect(await d.findByRole("button", { name: "Saving…" })).toBeDisabled();
  });

  it("the topic list opens with all four topics inside the dialog", async () => {
    const { user, dialog } = await openCreate();
    await user.click(within(dialog).getByRole("combobox", { name: /^Topic/ }));
    expect(within(dialog).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Choose a topic", "Addition", "Subtraction", "Counting", "Division",
    ]);
  });

  it("edit changes only text, answer, options and difficulty -- code and topic are shown, not editable", async () => {
    const user = userEvent.setup();
    createQuestion({ question_code: "CNT-9", topic: "Counting", difficulty: "Easy", question_text: "What comes after 4?", correct_answer: "5", options: ["5", "6"] });
    renderCompd("/compd?tab=questions");
    await user.click(await screen.findByRole("button", { name: 'Edit "What comes after 4?"' }));
    const d = within(screen.getByRole("dialog", { name: "Edit question" }));

    expect(d.getByText("CNT-9 · Counting")).toBeInTheDocument();
    expect(d.queryByLabelText("Question code")).not.toBeInTheDocument();
    expect(d.queryByRole("combobox", { name: /^Topic/ })).not.toBeInTheDocument();
    expect(d.getByLabelText("Question")).toHaveValue("What comes after 4?");

    await user.clear(d.getByLabelText("Answer"));
    await user.type(d.getByLabelText("Answer"), "7");
    await user.click(d.getByRole("button", { name: "Hard" }));
    await user.click(d.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Answer: 7")).toBeInTheDocument();
    expect(screen.getByText("Options: 5, 6, 7")).toBeInTheDocument();
    expect(screen.getByText("Hard")).toBeInTheDocument();
  });
});

describe("AI panel (U8)", () => {
  async function openPanel() {
    const user = userEvent.setup();
    renderCompd("/compd?tab=questions");
    await user.click((await screen.findAllByRole("button", { name: "Generate with AI" }))[0]!);
    return user;
  }

  it("shows the instructions hint, and drafts are editable before saving", async () => {
    const user = await openPanel();
    expect(screen.getByText("Don't include children's names or details.")).toBeInTheDocument();
    expect(screen.getByLabelText("Instructions (optional)")).toHaveAccessibleDescription(
      "Don't include children's names or details.",
    );
    await user.clear(screen.getByLabelText("How many questions (1-10)"));
    await user.type(screen.getByLabelText("How many questions (1-10)"), "3");
    await user.click(screen.getByRole("button", { name: "Generate" }));

    const drafts = await screen.findByRole("list", { name: "Question drafts" });
    expect(within(drafts).getAllByRole("listitem")).toHaveLength(3);
    const first = within(drafts).getAllByRole("listitem")[0]!;
    await user.clear(within(first).getByLabelText("Question"));
    await user.type(within(first).getByLabelText("Question"), "Edited by the teacher");
    expect(within(first).getByLabelText("Question")).toHaveValue("Edited by the teacher");
  });

  it("Save and Save all call create once per draft, and a saved draft says so", async () => {
    const create = vi.spyOn(compd, "createQuestion");
    const user = await openPanel();
    await user.clear(screen.getByLabelText("How many questions (1-10)"));
    await user.type(screen.getByLabelText("How many questions (1-10)"), "3");
    await user.click(screen.getByRole("button", { name: "Generate" }));
    const drafts = await screen.findByRole("list", { name: "Question drafts" });

    await user.click(within(within(drafts).getAllByRole("listitem")[0]!).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(create).toHaveBeenCalledTimes(1));
    expect(await within(drafts).findByText("Saved")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Save all (2)" }));
    await waitFor(() => expect(create).toHaveBeenCalledTimes(3));
    await waitFor(() => expect(within(drafts).getAllByText("Saved")).toHaveLength(3));
  });

  it("a 503 explains, and still offers Create manually", async () => {
    vi.spyOn(compd, "draftQuestions").mockRejectedValue(new CompdError(503, "unavailable"));
    const user = await openPanel();
    await user.click(screen.getByRole("button", { name: "Generate" }));
    expect(
      await screen.findByText("AI generation isn't available right now. You can still create questions by hand."),
    ).toBeInTheDocument();
    const alert = screen.getByRole("alert");
    await user.click(within(alert).getByRole("button", { name: "Create manually" }));
    expect(screen.getByRole("dialog", { name: "Create a question" })).toBeInTheDocument();
  });
});

describe("CompD errors stay on the CompD page (U10)", () => {
  function renderApp(path: string) {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[path]}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    );
  }

  it.each([403, 404, 500])("a %i on the Students tab shows ErrorState, never the account lock-out", async (status) => {
    vi.spyOn(compd, "getDashboard").mockRejectedValue(new CompdError(status, "failed"));
    renderApp("/compd");
    const message = status === 404 ? "This item isn't available." : "Couldn't load this. Check your connection and try again.";
    expect(await screen.findByText(message, undefined, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(screen.queryByText("This account can’t open the dashboard")).not.toBeInTheDocument();
  });

  it.each([403, 404, 500])("a %i on the student page shows ErrorState, never the account lock-out", async (status) => {
    vi.spyOn(compd, "getStudentProfiles").mockRejectedValue(new CompdError(status, "failed"));
    renderApp("/compd/students/s-amal");
    const message = status === 404 ? "This item isn't available." : "Couldn't load this. Check your connection and try again.";
    expect(await screen.findByText(message, undefined, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.queryByText("This account can’t open the dashboard")).not.toBeInTheDocument();
    // The rest of the page still works: the way back is there.
    expect(screen.getByRole("link", { name: "Back to Thinking Skills" })).toHaveAttribute("href", "/compd?tab=students");
  });
});
