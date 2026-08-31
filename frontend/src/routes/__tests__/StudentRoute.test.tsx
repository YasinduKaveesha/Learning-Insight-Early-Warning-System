import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { LearnerSnapshot, RecommendationDisplay } from "../../lib/presentation";
import StudentRoute from "../student/StudentRoute";
import { renderRoute } from "./testUtils";

vi.mock("../../api/client", () => ({
  client: {
    getHome: vi.fn(),
    getCohort: vi.fn(),
    getClassWatchList: vi.fn(),
    getWatchList: vi.fn(),
    getStudentOverview: vi.fn(),
    getStudentSessions: vi.fn(),
    getStudentRecommendations: vi.fn(),
    createClass: vi.fn(),
    getJoinRequests: vi.fn(),
    approveJoinRequest: vi.fn(),
    rejectJoinRequest: vi.fn(),
    getClassReports: vi.fn(),
  },
}));

const { client } = await import("../../api/client");

function makeSnapshot(overrides: Partial<LearnerSnapshot>): LearnerSnapshot {
  return {
    studentId: "s-1",
    displayName: "Amara",
    classId: "class-1",
    sessionNumber: 7,
    watchFlag: true,
    rankWithinSnapshot: 1,
    evidenceStatus: "sufficient_evidence",
    sessionsCompleted: 7,
    practiceTrajectory: { source: "practice_accuracy", state: "needs_attention" },
    explanation: "Subtraction has not improved across the last four sessions.",
    lastActiveDate: new Date().toISOString(),
    accuracySparkline: [0.6, 0.5, 0.45],
    engagementSparkline: [0.7, 0.68, 0.66],
    modelVersion: "v1",
    inferenceTimestamp: new Date().toISOString(),
    ...overrides,
  };
}

const SKILLS = [
  { skillId: "counting", displayName: "Counting", direction: "improving" as const, relativeLevel: 0.1, practiceCount: 4 },
  { skillId: "number_sense", displayName: "Number sense", direction: "not_moving" as const, relativeLevel: -0.05, practiceCount: 5 },
];
const BOUNDS = { counting: { min: -0.3, max: 0.3 }, number_sense: { min: -0.3, max: 0.3 } };

function renderStudent(studentId: string) {
  return renderRoute(<StudentRoute />, {
    path: "/students/:studentId",
    initialPath: `/students/${studentId}`,
  });
}

beforeEach(() => {
  vi.mocked(client.getStudentOverview).mockReset();
  vi.mocked(client.getStudentRecommendations).mockReset();
  vi.mocked(client.getStudentRecommendations).mockResolvedValue([]);
});

describe("StudentRoute — watching student", () => {
  it("renders status, why, skill progress and recent activity in order", async () => {
    vi.mocked(client.getStudentOverview).mockResolvedValue({
      snapshot: makeSnapshot({}),
      skills: SKILLS,
      disclosure: "d",
      className: "Grade 3 Blue",
      skillBounds: BOUNDS,
    });
    const { container } = renderStudent("s-1");
    await waitFor(() => expect(screen.getByText("Worth watching right now")).toBeInTheDocument());

    expect(screen.getByText(/Priority 1 in Grade 3 Blue/)).toBeInTheDocument();
    expect(screen.getByText("Why?")).toBeInTheDocument();
    expect(
      screen.getByText("Subtraction has not improved across the last four sessions."),
    ).toBeInTheDocument();
    expect(screen.getByText("Skill progress")).toBeInTheDocument();
    expect(screen.getByText("Recent activity")).toBeInTheDocument();

    // Order: status block before "Why?" before "Skill progress" before
    // "Recent activity" before "Suggestions".
    const text = container.textContent!;
    const iStatus = text.indexOf("Worth watching right now");
    const iWhy = text.indexOf("Why?");
    const iSkill = text.indexOf("Skill progress");
    const iActivity = text.indexOf("Recent activity");
    const iSuggestions = text.indexOf("Suggestions");
    expect(iStatus).toBeLessThan(iWhy);
    expect(iWhy).toBeLessThan(iSkill);
    expect(iSkill).toBeLessThan(iActivity);
    expect(iActivity).toBeLessThan(iSuggestions);
  });

  it("renders the practice trajectory chip and NO engagement trajectory state chip, only the series", async () => {
    vi.mocked(client.getStudentOverview).mockResolvedValue({
      snapshot: makeSnapshot({}),
      skills: SKILLS,
      disclosure: "d",
      className: "Grade 3 Blue",
      skillBounds: BOUNDS,
    });
    renderStudent("s-1");
    await waitFor(() => expect(screen.getByText(/Practice accuracy:/)).toBeInTheDocument());
    expect(screen.getByText("Game engagement")).toBeInTheDocument();
    // The withheld 3-state chip vocabulary must never appear attached to
    // "Game engagement" — only the practice chip carries those words.
    expect(screen.queryByText("Game engagement: needs attention ↓")).not.toBeInTheDocument();
    expect(screen.queryByText("Game engagement: improving ↑")).not.toBeInTheDocument();
    expect(screen.queryByText("Game engagement: stable →")).not.toBeInTheDocument();
  });
});

describe("StudentRoute — the two-signal path (plan §10)", () => {
  it("a student improving on practice accuracy but still flagged renders both, without one implying the other", async () => {
    vi.mocked(client.getStudentOverview).mockResolvedValue({
      snapshot: makeSnapshot({
        watchFlag: true,
        rankWithinSnapshot: 4,
        practiceTrajectory: { source: "practice_accuracy", state: "improving" },
      }),
      skills: SKILLS,
      disclosure: "d",
      className: "Grade 3 Blue",
      skillBounds: BOUNDS,
    });
    renderStudent("s-1");
    await waitFor(() => expect(screen.getByText("Worth watching right now")).toBeInTheDocument());
    expect(screen.getByText("Practice accuracy: improving ↑")).toBeInTheDocument();
    // Both render side by side; neither element's text claims the other.
    expect(screen.queryByText(/no concern/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/confirms/i)).not.toBeInTheDocument();
  });
});

describe("StudentRoute — Getting Started variant", () => {
  it("shows the personalised notice instead of a status block, and STILL renders skill progress and recent activity", async () => {
    vi.mocked(client.getStudentOverview).mockResolvedValue({
      snapshot: makeSnapshot({
        displayName: "Nimal",
        watchFlag: false,
        rankWithinSnapshot: null,
        evidenceStatus: "insufficient_exposure",
        sessionsCompleted: 2,
        practiceTrajectory: { source: "practice_accuracy", state: "unknown" },
        explanation: null,
      }),
      skills: SKILLS,
      disclosure: "d",
      className: "Grade 3 Blue",
      skillBounds: BOUNDS,
    });
    renderStudent("s-1");
    await waitFor(() =>
      expect(
        screen.getByText(
          "Nimal is still building a learning history — 2 of 3 sessions completed. More activity is needed before the system can identify a clear learning pattern.",
        ),
      ).toBeInTheDocument(),
    );

    // Status block (watch badge) and "Why?" heading are replaced, not
    // rendered alongside the notice.
    expect(screen.queryByText("Worth watching right now")).not.toBeInTheDocument();
    expect(screen.queryByText("No current concern identified")).not.toBeInTheDocument();
    expect(screen.queryByText("Why?")).not.toBeInTheDocument();

    // Skill progress and recent activity still render — descriptive data
    // is always available (plan §4.4, §8).
    expect(screen.getByText("Skill progress")).toBeInTheDocument();
    expect(screen.getByText("Recent activity")).toBeInTheDocument();
  });
});

describe("StudentRoute — Suggestions (Step 7: all four kinds + fallback)", () => {
  const BASE_REC: RecommendationDisplay = {
    recommendationId: "rec-1",
    kind: "practice",
    targetSkillDisplayName: "Counting",
    evidenceSummary: "Counting has fewer practice attempts than other skills this month.",
    status: "pending",
    modifiedActionSummary: null,
    expiresAfterSession: 12,
  };

  function overviewFor(studentId: string) {
    return {
      snapshot: makeSnapshot({ studentId }),
      skills: SKILLS,
      disclosure: "d",
      className: "Grade 3 Blue",
      skillBounds: BOUNDS,
    };
  }

  it.each(["practice", "review", "try_again", "monitor_progress"])(
    "renders the known kind '%s' through the lookup",
    async (kind) => {
      vi.mocked(client.getStudentOverview).mockResolvedValue(overviewFor("s-1"));
      vi.mocked(client.getStudentRecommendations).mockResolvedValue([{ ...BASE_REC, kind }]);
      renderStudent("s-1");
      await waitFor(() => expect(screen.getByText("Suggestions")).toBeInTheDocument());
      expect(screen.getByText(BASE_REC.evidenceSummary)).toBeInTheDocument();
    },
  );

  it("an unrecognised kind falls back to a readable label and does not throw", async () => {
    vi.mocked(client.getStudentOverview).mockResolvedValue(overviewFor("s-1"));
    vi.mocked(client.getStudentRecommendations).mockResolvedValue([
      { ...BASE_REC, kind: "adjust_difficulty" },
    ]);
    expect(() => renderStudent("s-1")).not.toThrow();
    await waitFor(() => expect(screen.getByText("Suggestions")).toBeInTheDocument());
    expect(screen.getByText(/^Suggestion —/)).toBeInTheDocument();
  });

  it("evidence is inline with the action, expiry is shown, and it is marked 'Not yet applied'", async () => {
    vi.mocked(client.getStudentOverview).mockResolvedValue(overviewFor("s-1"));
    vi.mocked(client.getStudentRecommendations).mockResolvedValue([BASE_REC]);
    renderStudent("s-1");
    await waitFor(() => expect(screen.getByText(BASE_REC.evidenceSummary)).toBeInTheDocument());
    expect(screen.getByText(/Not yet applied/)).toBeInTheDocument();
    expect(screen.getByText(/Expires after session 12/)).toBeInTheDocument();
  });

  it("there is no 'Accept all' control anywhere on the screen", async () => {
    vi.mocked(client.getStudentOverview).mockResolvedValue(overviewFor("s-1"));
    vi.mocked(client.getStudentRecommendations).mockResolvedValue([
      BASE_REC,
      { ...BASE_REC, recommendationId: "rec-2", kind: "review" },
    ]);
    renderStudent("s-1");
    await waitFor(() => expect(screen.getByText("Suggestions")).toBeInTheDocument());
    expect(screen.queryByText(/accept all/i)).not.toBeInTheDocument();
  });

  it("Modify captures what the teacher changed it to", async () => {
    vi.mocked(client.getStudentOverview).mockResolvedValue(overviewFor("s-1"));
    vi.mocked(client.getStudentRecommendations).mockResolvedValue([BASE_REC]);
    renderStudent("s-1");
    await waitFor(() => expect(screen.getByText(BASE_REC.evidenceSummary)).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: "Modify" }));
    await userEvent.type(screen.getByRole("textbox"), "Try place value instead");
    await userEvent.click(screen.getByRole("button", { name: "Save change" }));

    await waitFor(() => expect(screen.getByText(/Modified: Try place value instead/)).toBeInTheDocument());
  });

  it("Accept/Modify/Dismiss are equally weighted and visually distinct", async () => {
    vi.mocked(client.getStudentOverview).mockResolvedValue(overviewFor("s-1"));
    vi.mocked(client.getStudentRecommendations).mockResolvedValue([BASE_REC]);
    renderStudent("s-1");
    await waitFor(() => expect(screen.getByText(BASE_REC.evidenceSummary)).toBeInTheDocument());
    const accept = screen.getByRole("button", { name: "Accept" });
    const modify = screen.getByRole("button", { name: "Modify" });
    const dismiss = screen.getByRole("button", { name: "Dismiss" });
    expect(accept.className).not.toBe(modify.className);
    expect(modify.className).not.toBe(dismiss.className);
  });
});

describe("StudentRoute — four states", () => {
  it("loading renders skeletons, not a spinner", () => {
    vi.mocked(client.getStudentOverview).mockReturnValue(new Promise(() => {}));
    renderStudent("s-1");
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
  });

  it("error state says what failed and offers retry, never a raw error string", async () => {
    vi.mocked(client.getStudentOverview).mockRejectedValue(new Error("500 boom"));
    renderStudent("s-1");
    await waitFor(() => expect(screen.getByText(/Couldn't load this student/)).toBeInTheDocument());
    expect(screen.queryByText(/500/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});

describe("StudentRoute — framing, disclosure, forbidden vocabulary", () => {
  it("renders the framing line and the API-sourced disclosure", async () => {
    vi.mocked(client.getStudentOverview).mockResolvedValue({
      snapshot: makeSnapshot({}),
      skills: SKILLS,
      disclosure: "Literature-informed synthetic data — not clinical evidence.",
      className: "Grade 3 Blue",
      skillBounds: BOUNDS,
    });
    renderStudent("s-1");
    expect(screen.getByText("The system flags learners for teacher review.")).toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.getByText("Literature-informed synthetic data — not clinical evidence."),
      ).toBeInTheDocument(),
    );
  });

  const FORBIDDEN = [
    "diagnos",
    "dyscalculia",
    "disorder",
    "deficit",
    "disability",
    "impairment",
    "screening",
    "detected",
    "population",
    "dd_subtype",
    "confidence",
  ];

  it("renders no banned vocabulary or probability/score in the loaded state", async () => {
    vi.mocked(client.getStudentOverview).mockResolvedValue({
      snapshot: makeSnapshot({}),
      skills: SKILLS,
      disclosure: "d",
      className: "Grade 3 Blue",
      skillBounds: BOUNDS,
    });
    const { container } = renderStudent("s-1");
    await waitFor(() => expect(screen.getByText("Skill progress")).toBeInTheDocument());
    const text = container.textContent!.toLowerCase();
    for (const term of FORBIDDEN) expect(text).not.toContain(term);
  });

  it("renders no banned vocabulary in the Getting Started notice", async () => {
    vi.mocked(client.getStudentOverview).mockResolvedValue({
      snapshot: makeSnapshot({
        evidenceStatus: "insufficient_exposure",
        sessionsCompleted: 1,
        practiceTrajectory: { source: "practice_accuracy", state: "unknown" },
      }),
      skills: SKILLS,
      disclosure: "d",
      className: "Grade 3 Blue",
      skillBounds: BOUNDS,
    });
    const { container } = renderStudent("s-1");
    await waitFor(() => expect(screen.getByText(/still building a learning history/)).toBeInTheDocument());
    const text = container.textContent!.toLowerCase();
    for (const term of FORBIDDEN) expect(text).not.toContain(term);
  });
});
