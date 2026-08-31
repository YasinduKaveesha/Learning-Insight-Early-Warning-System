import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { LearnerSnapshot, SessionEntry } from "../../lib/presentation";
import StudentSessionsRoute from "../student-sessions/StudentSessionsRoute";
import { renderRoute } from "./testUtils";

vi.mock("../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../api/client")>("../../api/client");
  return {
    DuplicateClassNameError: actual.DuplicateClassNameError,
    isDuplicateClassNameError: actual.isDuplicateClassNameError,
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
  };
});

const { client } = await import("../../api/client");

const SNAPSHOT: LearnerSnapshot = {
  studentId: "s-1",
  displayName: "Nimal",
  classId: "class-1",
  sessionNumber: 7,
  watchFlag: false,
  rankWithinSnapshot: null,
  evidenceStatus: "sufficient_evidence",
  sessionsCompleted: 7,
  practiceTrajectory: { source: "practice_accuracy", state: "stable" },
  explanation: null,
  lastActiveDate: new Date().toISOString(),
  accuracySparkline: [],
  engagementSparkline: [],
  modelVersion: "v1",
  inferenceTimestamp: new Date().toISOString(),
};

function makeSession(overrides: Partial<SessionEntry>): SessionEntry {
  return {
    sessionNumber: 1,
    date: "2026-08-24T00:00:00.000Z",
    practice: { present: true, accuracy: 0.8, pace: "typical", hintsUsed: 1 },
    games: {
      present: true,
      dataComplete: true,
      state: "on_target",
      stateReason: null,
      engagementDriver: "steady completion",
      frustrationDriver: null,
    },
    ...overrides,
  };
}

function renderSessions() {
  return renderRoute(<StudentSessionsRoute />, {
    path: "/students/:studentId/sessions",
    initialPath: "/students/s-1/sessions",
  });
}

beforeEach(() => {
  vi.mocked(client.getStudentOverview).mockReset();
  vi.mocked(client.getStudentSessions).mockReset();
  vi.mocked(client.getStudentOverview).mockResolvedValue({
    snapshot: SNAPSHOT,
    skills: [],
    disclosure: "Literature-informed synthetic data — not clinical evidence.",
    className: "Grade 3 Blue",
    skillBounds: {},
  });
});

describe("StudentSessionsRoute — the missing-data path (plan §10)", () => {
  it("a session with no Component C payload renders 'No activity recorded', never a zero", async () => {
    vi.mocked(client.getStudentSessions).mockResolvedValue([
      makeSession({
        sessionNumber: 6,
        games: {
          present: false,
          dataComplete: true,
          state: null,
          stateReason: null,
          engagementDriver: null,
          frustrationDriver: null,
        },
      }),
    ]);
    renderSessions();
    await waitFor(() => expect(screen.getByText("No activity recorded")).toBeInTheDocument());
    expect(screen.queryByText(/^0$/)).not.toBeInTheDocument();
  });

  it("a session with incomplete telemetry renders 'Activity data incomplete for this session'", async () => {
    vi.mocked(client.getStudentSessions).mockResolvedValue([
      makeSession({
        sessionNumber: 7,
        games: {
          present: true,
          dataComplete: false,
          state: null,
          stateReason: "telemetry_gap",
          engagementDriver: null,
          frustrationDriver: null,
        },
      }),
    ]);
    renderSessions();
    await waitFor(() =>
      expect(
        screen.getByText("Activity data incomplete for this session"),
      ).toBeInTheDocument(),
    );
    expect(screen.queryByText(/disengag/i)).not.toBeInTheDocument();
  });

  it("the two messages are distinct and neither renders for the other case", async () => {
    vi.mocked(client.getStudentSessions).mockResolvedValue([
      makeSession({
        sessionNumber: 6,
        games: {
          present: false,
          dataComplete: true,
          state: null,
          stateReason: null,
          engagementDriver: null,
          frustrationDriver: null,
        },
      }),
      makeSession({
        sessionNumber: 7,
        games: {
          present: true,
          dataComplete: false,
          state: null,
          stateReason: "telemetry_gap",
          engagementDriver: null,
          frustrationDriver: null,
        },
      }),
    ]);
    renderSessions();
    await waitFor(() => expect(screen.getByText("No activity recorded")).toBeInTheDocument());
    expect(
      screen.getByText("Activity data incomplete for this session"),
    ).toBeInTheDocument();
    // Session 6 (no-C) does not also carry the incomplete message, and vice
    // versa — each session card renders exactly one gap message.
    const session6Card = screen.getByText("Session 6").closest("div")!.parentElement!;
    const session7Card = screen.getByText("Session 7").closest("div")!.parentElement!;
    expect(session6Card.textContent).not.toContain("incomplete");
    expect(session7Card.textContent).not.toContain("No activity recorded");
  });
});

describe("StudentSessionsRoute — B and C never merged", () => {
  it("renders Practice (B) and Games (C) as separate labelled blocks, never one figure", async () => {
    vi.mocked(client.getStudentSessions).mockResolvedValue([
      makeSession({ sessionNumber: 5 }),
    ]);
    renderSessions();
    await waitFor(() => expect(screen.getByText("Practice (B)")).toBeInTheDocument());
    expect(screen.getByText("Games (C)")).toBeInTheDocument();
  });

  it("shows the contributing component for engagement/frustration, not only a composite", async () => {
    vi.mocked(client.getStudentSessions).mockResolvedValue([
      makeSession({
        sessionNumber: 5,
        games: {
          present: true,
          dataComplete: true,
          state: "on_target",
          stateReason: null,
          engagementDriver: "steady completion",
          frustrationDriver: "error_run",
        },
      }),
    ]);
    renderSessions();
    await waitFor(() => expect(screen.getByText(/Engagement: steady completion/)).toBeInTheDocument());
    expect(screen.getByText(/Frustration: error_run/)).toBeInTheDocument();
  });
});

describe("StudentSessionsRoute — session numbers render exactly as supplied", () => {
  it("renders a gapped sequence in the order given, without renumbering", async () => {
    vi.mocked(client.getStudentSessions).mockResolvedValue([
      makeSession({ sessionNumber: 3 }),
      makeSession({ sessionNumber: 4 }),
      makeSession({ sessionNumber: 6 }), // gap: no session 5
      makeSession({ sessionNumber: 9 }), // gap: no sessions 7, 8
    ]);
    renderSessions();
    await waitFor(() => expect(screen.getByText("Session 3")).toBeInTheDocument());
    expect(screen.getByText("Session 4")).toBeInTheDocument();
    expect(screen.getByText("Session 6")).toBeInTheDocument();
    expect(screen.getByText("Session 9")).toBeInTheDocument();
    expect(screen.queryByText("Session 1")).not.toBeInTheDocument();
    expect(screen.queryByText("Session 5")).not.toBeInTheDocument();
    expect(screen.queryByText("Session 7")).not.toBeInTheDocument();
  });
});

describe("StudentSessionsRoute — four states", () => {
  it("loading renders skeletons, not a spinner", () => {
    vi.mocked(client.getStudentSessions).mockReturnValue(new Promise(() => {}));
    renderSessions();
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
  });

  it("empty state says what would fill it", async () => {
    vi.mocked(client.getStudentSessions).mockResolvedValue([]);
    renderSessions();
    await waitFor(() =>
      expect(screen.getByText("No sessions recorded yet.")).toBeInTheDocument(),
    );
  });

  it("error state says what failed and offers retry, never a raw error string", async () => {
    vi.mocked(client.getStudentSessions).mockRejectedValue(new Error("500 Internal Server Error"));
    renderSessions();
    await waitFor(() =>
      expect(screen.getByText(/Couldn't load session history/)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/500/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});

describe("StudentSessionsRoute — framing, disclosure, forbidden vocabulary", () => {
  it("renders the framing line and the API-sourced disclosure", async () => {
    vi.mocked(client.getStudentSessions).mockResolvedValue([makeSession({ sessionNumber: 1 })]);
    renderSessions();
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
    vi.mocked(client.getStudentSessions).mockResolvedValue([makeSession({ sessionNumber: 1 })]);
    const { container } = renderSessions();
    await waitFor(() => expect(screen.getByText("Session 1")).toBeInTheDocument());
    const text = container.textContent!.toLowerCase();
    for (const term of FORBIDDEN) expect(text).not.toContain(term);
  });

  it("renders no banned vocabulary in the empty state", async () => {
    vi.mocked(client.getStudentSessions).mockResolvedValue([]);
    const { container } = renderSessions();
    await waitFor(() => expect(screen.getByText("No sessions recorded yet.")).toBeInTheDocument());
    const text = container.textContent!.toLowerCase();
    for (const term of FORBIDDEN) expect(text).not.toContain(term);
  });
});
