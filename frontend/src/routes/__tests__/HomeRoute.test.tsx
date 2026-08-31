import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import HomeRoute from "../home/HomeRoute";
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
  },
}));

const { client } = await import("../../api/client");

const HOME_SUMMARY = {
  teacherName: "Ms Perera",
  studentsToWatch: 7,
  activeStudents: 83,
  classCount: 3,
  gettingStarted: 9,
  classes: [
    { classId: "class-1", name: "Grade 3 Blue", grade: "GRADE_3" as const, studentCount: 28, toWatchCount: 6 },
  ],
  disclosure: "Literature-informed synthetic data — not clinical evidence.",
};

function renderHome() {
  return renderRoute(<HomeRoute />, { path: "/", initialPath: "/" });
}

beforeEach(() => {
  vi.mocked(client.getHome).mockReset();
});

describe("HomeRoute — the watch card", () => {
  it("shows both the count and the total", async () => {
    vi.mocked(client.getHome).mockResolvedValue(HOME_SUMMARY);
    renderHome();
    await waitFor(() => expect(screen.getByText("7")).toBeInTheDocument());
    expect(screen.getByText("of 83 students")).toBeInTheDocument();
    expect(screen.getByText("Based on recent learning activity")).toBeInTheDocument();
  });

  it("links to the watch list", async () => {
    vi.mocked(client.getHome).mockResolvedValue(HOME_SUMMARY);
    renderHome();
    await waitFor(() => expect(screen.getByText("7")).toBeInTheDocument());
    const link = screen.getByText("View watch list →").closest("a")!;
    expect(link).toHaveAttribute("href", "/watch");
  });
});

describe("HomeRoute — stat tiles and classes", () => {
  it("shows Active Students, Classes, Getting Started with an info explanation", async () => {
    vi.mocked(client.getHome).mockResolvedValue(HOME_SUMMARY);
    renderHome();
    await waitFor(() => expect(screen.getByText("Active Students")).toBeInTheDocument());
    expect(screen.getByText("Classes")).toBeInTheDocument();
    expect(screen.getByText("Getting Started")).toBeInTheDocument();
    expect(
      screen.getByLabelText(/still building their learning history/),
    ).toBeInTheDocument();
  });

  it("renders class cards with student count and to-watch count", async () => {
    vi.mocked(client.getHome).mockResolvedValue(HOME_SUMMARY);
    renderHome();
    await waitFor(() => expect(screen.getByText("Grade 3 Blue")).toBeInTheDocument());
    expect(screen.getByText(/28 students/)).toBeInTheDocument();
    expect(screen.getByText(/6 to watch/)).toBeInTheDocument();
  });
});

describe("HomeRoute — four states", () => {
  it("loading renders skeletons, not a spinner", () => {
    vi.mocked(client.getHome).mockReturnValue(new Promise(() => {}));
    renderHome();
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
  });

  it("empty (no classes) shows the full-width primary create-class card", async () => {
    vi.mocked(client.getHome).mockResolvedValue({ ...HOME_SUMMARY, classCount: 0, classes: [] });
    renderHome();
    await waitFor(() =>
      expect(screen.getByText("Create your first class to get started.")).toBeInTheDocument(),
    );
  });

  it("error state says what failed and offers retry, never a raw error string", async () => {
    vi.mocked(client.getHome).mockRejectedValue(new Error("fetch failed: ECONNREFUSED"));
    renderHome();
    await waitFor(() => expect(screen.getByText(/Couldn't load your dashboard/)).toBeInTheDocument());
    expect(screen.queryByText(/ECONNREFUSED/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});

describe("HomeRoute — framing, disclosure, and forbidden vocabulary", () => {
  it("renders the framing line and the API-sourced disclosure", async () => {
    vi.mocked(client.getHome).mockResolvedValue(HOME_SUMMARY);
    renderHome();
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

  it("renders no banned vocabulary or probability/score", async () => {
    vi.mocked(client.getHome).mockResolvedValue(HOME_SUMMARY);
    const { container } = renderHome();
    await waitFor(() => expect(screen.getByText("Grade 3 Blue")).toBeInTheDocument());
    const text = container.textContent!.toLowerCase();
    for (const term of FORBIDDEN) expect(text).not.toContain(term);
  });
});
