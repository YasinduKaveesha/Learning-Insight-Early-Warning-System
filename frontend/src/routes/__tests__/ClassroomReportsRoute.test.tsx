import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ClassroomReportsRoute from "../classroom-reports/ClassroomReportsRoute";
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

const REPORTS = {
  disclosure: "Literature-informed synthetic data — not clinical evidence.",
  className: "Grade 3 Blue",
  classLearningProgress: { sessionNumbers: [1, 2, 3, 4, 5], values: [0.5, 0.52, 0.55, 0.58, 0.6] },
  studentsToWatchOverTime: {
    sessionNumbers: [3, 5, 7, 9, 11],
    counts: [0, 1, 2, 3, 4],
  },
  earlyWarningTrend: {
    sessionNumbers: [3, 5, 7, 9, 11],
    flagRates: [0.04, 0.2, 0.4, 0.5, 0.6],
    explanation:
      "This shows the share of students the system would have flagged for review by each point in the study.",
  },
  participation: [
    { bucketLabel: "1–2 sessions", studentCount: 2 },
    { bucketLabel: "3–5 sessions", studentCount: 3 },
    { bucketLabel: "6+ sessions", studentCount: 3 },
  ],
};

function renderReports() {
  return renderRoute(<ClassroomReportsRoute />, {
    path: "/classes/:classId/reports",
    initialPath: "/classes/class-1/reports",
  });
}

beforeEach(() => {
  vi.mocked(client.getClassReports).mockReset();
});

describe("ClassroomReportsRoute — four sections", () => {
  it("renders class learning progress, students to watch over time, early-warning trend and participation", async () => {
    vi.mocked(client.getClassReports).mockResolvedValue(REPORTS);
    renderReports();
    await waitFor(() => expect(screen.getByText("Class learning progress")).toBeInTheDocument());
    expect(screen.getByText("Students to watch over time")).toBeInTheDocument();
    expect(screen.getByText("Early-warning trend")).toBeInTheDocument();
    expect(screen.getByText("Participation")).toBeInTheDocument();
  });

  it("the early-warning trend carries its plain-language explanation", async () => {
    vi.mocked(client.getClassReports).mockResolvedValue(REPORTS);
    renderReports();
    await waitFor(() =>
      expect(screen.getByText(REPORTS.earlyWarningTrend.explanation)).toBeInTheDocument(),
    );
  });

  it("every chart has an accompanying trend sentence", async () => {
    vi.mocked(client.getClassReports).mockResolvedValue(REPORTS);
    const { container } = renderReports();
    await waitFor(() => expect(screen.getByText("Class learning progress")).toBeInTheDocument());
    // Three Chart components render (progress, watch-over-time, early-warning).
    const sentences = [
      /Class average practice accuracy/,
      /number of students to watch/,
      /share of students flagged/,
    ];
    for (const pattern of sentences) {
      expect(container.textContent).toMatch(pattern);
    }
  });

  it("participation shows a real breakdown of session counts", async () => {
    vi.mocked(client.getClassReports).mockResolvedValue(REPORTS);
    renderReports();
    await waitFor(() => expect(screen.getByText("1–2 sessions")).toBeInTheDocument());
    expect(screen.getByText("3–5 sessions")).toBeInTheDocument();
    expect(screen.getByText("6+ sessions")).toBeInTheDocument();
  });
});

describe("ClassroomReportsRoute — no research metric ever renders", () => {
  // The explicit anti-leak test the task calls for: this screen is the most
  // likely place in the app for a research metric to leak in, because the
  // underlying numbers are right there in the fixtures. Assert by TERM and
  // by VALUE — a metric can leak as a label ("AUC: 0.81") or as a bare
  // number formatted to look like one.
  const FORBIDDEN_TERMS = [
    "precision",
    "recall",
    "f1",
    "f-1",
    "auc",
    "lift",
    "calibration",
    "confusion matrix",
    "brier",
  ];

  it("renders no research-metric terms in the loaded state", async () => {
    vi.mocked(client.getClassReports).mockResolvedValue(REPORTS);
    const { container } = renderReports();
    await waitFor(() => expect(screen.getByText("Class learning progress")).toBeInTheDocument());
    const text = container.textContent!.toLowerCase();
    for (const term of FORBIDDEN_TERMS) expect(text).not.toContain(term);
  });

  it("renders no flagRate/probability VALUE as a percentage or decimal-confidence figure", async () => {
    vi.mocked(client.getClassReports).mockResolvedValue(REPORTS);
    const { container } = renderReports();
    await waitFor(() => expect(screen.getByText("Class learning progress")).toBeInTheDocument());
    const text = container.textContent!;
    // None of the raw flagRate/accuracy decimals (0.04, 0.2, 0.5, 0.6, etc.)
    // or a percentage rendering of them should appear as visible text — the
    // chart conveys shape, the trend sentence conveys direction in words.
    expect(text).not.toMatch(/0\.\d{1,4}/);
    expect(text).not.toMatch(/\d{1,3}%/);
  });

  it("the mock response itself carries no research-metric field", () => {
    const keys = JSON.stringify(REPORTS).toLowerCase();
    for (const term of FORBIDDEN_TERMS) expect(keys).not.toContain(term);
  });
});

describe("ClassroomReportsRoute — four states", () => {
  it("loading renders skeletons, not a spinner", () => {
    vi.mocked(client.getClassReports).mockReturnValue(new Promise(() => {}));
    renderReports();
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
  });

  it("error state says what failed and offers retry, never a raw error string", async () => {
    vi.mocked(client.getClassReports).mockRejectedValue(new Error("500 Internal Server Error"));
    renderReports();
    await waitFor(() => expect(screen.getByText(/Couldn't load reports/)).toBeInTheDocument());
    expect(screen.queryByText(/500/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});

describe("ClassroomReportsRoute — framing, disclosure, forbidden vocabulary", () => {
  it("renders the framing line and the API-sourced disclosure", async () => {
    vi.mocked(client.getClassReports).mockResolvedValue(REPORTS);
    renderReports();
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

  it("renders no banned vocabulary in the loaded state", async () => {
    vi.mocked(client.getClassReports).mockResolvedValue(REPORTS);
    const { container } = renderReports();
    await waitFor(() => expect(screen.getByText("Class learning progress")).toBeInTheDocument());
    const text = container.textContent!.toLowerCase();
    for (const term of FORBIDDEN) expect(text).not.toContain(term);
  });

  it("renders no banned vocabulary in the error state", async () => {
    vi.mocked(client.getClassReports).mockRejectedValue(new Error("boom"));
    const { container } = renderReports();
    await waitFor(() => expect(screen.getByText(/Couldn't load reports/)).toBeInTheDocument());
    const text = container.textContent!.toLowerCase();
    for (const term of FORBIDDEN) expect(text).not.toContain(term);
  });
});
