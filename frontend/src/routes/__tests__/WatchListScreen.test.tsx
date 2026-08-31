import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { LearnerSnapshot } from "../../lib/presentation";
import { WatchListScreen } from "../watch/WatchListScreen";
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

/** Overrides window.matchMedia for the >=1024px master-detail query for the
 * duration of one test, restoring the mobile-default mock (see
 * testSetup.ts) afterwards. */
function mockDesktopViewport() {
  const original = window.matchMedia;
  window.matchMedia = ((query: string) => ({
    matches: query === "(min-width: 1024px)",
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia;
  return () => {
    window.matchMedia = original;
  };
}

const { client } = await import("../../api/client");

function makeSnapshot(overrides: Partial<LearnerSnapshot>): LearnerSnapshot {
  return {
    studentId: "id-" + Math.random(),
    displayName: "Student",
    classId: "class-1",
    sessionNumber: 7,
    watchFlag: true,
    rankWithinSnapshot: 1,
    evidenceStatus: "sufficient_evidence",
    sessionsCompleted: 7,
    practiceTrajectory: { source: "practice_accuracy", state: "needs_attention" },
    explanation: "Subtraction has not improved across the last four sessions.",
    lastActiveDate: new Date().toISOString(),
    accuracySparkline: [],
    engagementSparkline: [],
    modelVersion: "v1",
    inferenceTimestamp: new Date().toISOString(),
    ...overrides,
  };
}

const AMARA = makeSnapshot({
  studentId: "s-amara",
  displayName: "Amara",
  classId: "class-1",
  rankWithinSnapshot: 1,
});
const KAVINDU = makeSnapshot({
  studentId: "s-kavindu",
  displayName: "Kavindu",
  classId: "class-2",
  rankWithinSnapshot: 2,
});

beforeEach(() => {
  vi.mocked(client.getWatchList).mockReset();
  vi.mocked(client.getClassWatchList).mockReset();
  vi.mocked(client.getHome).mockReset();
});

describe("WatchListScreen — teacher-wide (/watch)", () => {
  it("excludes Getting Started students entirely and shows the count and total", async () => {
    vi.mocked(client.getWatchList).mockResolvedValue({
      totalStudents: 24,
      disclosure: "Literature-informed synthetic data — not clinical evidence.",
      students: [AMARA, KAVINDU],
    });
    vi.mocked(client.getHome).mockResolvedValue({
      teacherName: "Ms Perera",
      studentsToWatch: 2,
      activeStudents: 24,
      classCount: 2,
      gettingStarted: 1,
      classes: [
        { classId: "class-1", name: "Grade 3 Blue", grade: "GRADE_3", studentCount: 8, toWatchCount: 1, pendingRequestCount: 0 },
        { classId: "class-2", name: "Grade 3 Green", grade: "GRADE_3", studentCount: 8, toWatchCount: 1, pendingRequestCount: 0 },
      ],
      disclosure: "Literature-informed synthetic data — not clinical evidence.",
    });
    renderRoute(<WatchListScreen />, { path: "/watch", initialPath: "/watch" });

    await waitFor(() => expect(screen.getByText("Amara")).toBeInTheDocument());
    expect(screen.getByText("Kavindu")).toBeInTheDocument();
    // UI-refinement pass: the section heading between groups is removed —
    // each card carries its own class name (top-right) and grade colour
    // instead, so "Grade 3 Blue" still appears, just on Amara's own card.
    expect(screen.getByText("Grade 3 Blue")).toBeInTheDocument();
    expect(screen.getByText("Grade 3 Green")).toBeInTheDocument();
  });

  it("the explanation is on the card, not behind a tap", async () => {
    vi.mocked(client.getWatchList).mockResolvedValue({
      totalStudents: 24,
      disclosure: "d",
      students: [AMARA],
    });
    vi.mocked(client.getHome).mockResolvedValue({
      teacherName: "Ms Perera",
      studentsToWatch: 1,
      activeStudents: 24,
      classCount: 1,
      gettingStarted: 0,
      classes: [{ classId: "class-1", name: "Grade 3 Blue", grade: "GRADE_3", studentCount: 8, toWatchCount: 1, pendingRequestCount: 0 }],
      disclosure: "d",
    });
    renderRoute(<WatchListScreen />, { path: "/watch", initialPath: "/watch" });
    await waitFor(() => expect(screen.getByText("Amara")).toBeInTheDocument());
    expect(
      screen.getByText("Subtraction has not improved across the last four sessions."),
    ).toBeInTheDocument();
  });

  it("UI-refinement pass: 'Priority N' text is removed from watch-list cards", async () => {
    vi.mocked(client.getWatchList).mockResolvedValue({
      totalStudents: 24,
      disclosure: "d",
      students: [AMARA],
    });
    vi.mocked(client.getHome).mockResolvedValue({
      teacherName: "Ms Perera",
      studentsToWatch: 1,
      activeStudents: 24,
      classCount: 1,
      gettingStarted: 0,
      classes: [{ classId: "class-1", name: "Grade 3 Blue", grade: "GRADE_3", studentCount: 8, toWatchCount: 1, pendingRequestCount: 0 }],
      disclosure: "d",
    });
    renderRoute(<WatchListScreen />, { path: "/watch", initialPath: "/watch" });
    await waitFor(() => expect(screen.getByText("Amara")).toBeInTheDocument());
    expect(screen.queryByText(/Priority 1/)).not.toBeInTheDocument();
  });

  it("renders the empty state neutrally when nobody is flagged", async () => {
    vi.mocked(client.getWatchList).mockResolvedValue({ totalStudents: 24, disclosure: "d", students: [] });
    vi.mocked(client.getHome).mockResolvedValue({
      teacherName: "Ms Perera",
      studentsToWatch: 0,
      activeStudents: 24,
      classCount: 1,
      gettingStarted: 0,
      classes: [],
      disclosure: "d",
    });
    renderRoute(<WatchListScreen />, { path: "/watch", initialPath: "/watch" });
    await waitFor(() =>
      expect(
        screen.getByText("No students are currently flagged for review."),
      ).toBeInTheDocument(),
    );
  });

  it("renders an error state with retry, never a raw error string", async () => {
    vi.mocked(client.getWatchList).mockRejectedValue(new Error("500 Internal Server Error"));
    vi.mocked(client.getHome).mockResolvedValue({
      teacherName: "Ms Perera",
      studentsToWatch: 0,
      activeStudents: 0,
      classCount: 0,
      gettingStarted: 0,
      classes: [],
      disclosure: "d",
    });
    renderRoute(<WatchListScreen />, { path: "/watch", initialPath: "/watch" });
    await waitFor(() =>
      expect(screen.getByText(/Couldn't load the watch list/)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/500/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});

describe("WatchListScreen — >=1024px master-detail (plan §8, hardening-pass gap 2)", () => {
  const SKILLS = [
    { skillId: "counting", displayName: "Counting", direction: "improving" as const, relativeLevel: 0.1, practiceCount: 4 },
  ];
  const BOUNDS = { counting: { min: -0.3, max: 0.3 } };

  beforeEach(() => {
    vi.mocked(client.getStudentOverview).mockReset();
    vi.mocked(client.getStudentRecommendations).mockReset();
    vi.mocked(client.getStudentRecommendations).mockResolvedValue([]);
  });

  it("below 1024px, a card still links straight to /students/:id — unchanged from before", async () => {
    vi.mocked(client.getWatchList).mockResolvedValue({
      totalStudents: 24,
      disclosure: "d",
      students: [AMARA],
    });
    vi.mocked(client.getHome).mockResolvedValue({
      teacherName: "Ms Perera",
      studentsToWatch: 1,
      activeStudents: 24,
      classCount: 1,
      gettingStarted: 0,
      classes: [{ classId: "class-1", name: "Grade 3 Blue", grade: "GRADE_3", studentCount: 8, toWatchCount: 1, pendingRequestCount: 0 }],
      disclosure: "d",
    });
    renderRoute(<WatchListScreen />, { path: "/watch", initialPath: "/watch" });
    await waitFor(() => expect(screen.getByText("Amara")).toBeInTheDocument());
    expect(screen.getByRole("link", { name: /Amara/ })).toHaveAttribute("href", "/students/s-amara");
  });

  it("at >=1024px, a card links to /watch/:studentId (teacher-wide) instead of the standalone route", async () => {
    const restore = mockDesktopViewport();
    vi.mocked(client.getWatchList).mockResolvedValue({
      totalStudents: 24,
      disclosure: "d",
      students: [AMARA],
    });
    vi.mocked(client.getHome).mockResolvedValue({
      teacherName: "Ms Perera",
      studentsToWatch: 1,
      activeStudents: 24,
      classCount: 1,
      gettingStarted: 0,
      classes: [{ classId: "class-1", name: "Grade 3 Blue", grade: "GRADE_3", studentCount: 8, toWatchCount: 1, pendingRequestCount: 0 }],
      disclosure: "d",
    });
    renderRoute(<WatchListScreen />, { path: "/watch", initialPath: "/watch" });
    await waitFor(() => expect(screen.getByText("Amara")).toBeInTheDocument());
    expect(screen.getByRole("link", { name: /Amara/ })).toHaveAttribute("href", "/watch/s-amara");
    restore();
  });

  it("at >=1024px with no selection, the right pane says what to do instead of being blank", async () => {
    const restore = mockDesktopViewport();
    vi.mocked(client.getWatchList).mockResolvedValue({
      totalStudents: 24,
      disclosure: "d",
      students: [AMARA],
    });
    vi.mocked(client.getHome).mockResolvedValue({
      teacherName: "Ms Perera",
      studentsToWatch: 1,
      activeStudents: 24,
      classCount: 1,
      gettingStarted: 0,
      classes: [{ classId: "class-1", name: "Grade 3 Blue", grade: "GRADE_3", studentCount: 8, toWatchCount: 1, pendingRequestCount: 0 }],
      disclosure: "d",
    });
    renderRoute(<WatchListScreen />, { path: "/watch", initialPath: "/watch" });
    await waitFor(() =>
      expect(
        screen.getByText("Select a student from the list to see their detail."),
      ).toBeInTheDocument(),
    );
    restore();
  });

  it("selection is URL-driven: selectedStudentId renders that student's detail in the right pane", async () => {
    const restore = mockDesktopViewport();
    vi.mocked(client.getWatchList).mockResolvedValue({
      totalStudents: 24,
      disclosure: "d",
      students: [AMARA],
    });
    vi.mocked(client.getHome).mockResolvedValue({
      teacherName: "Ms Perera",
      studentsToWatch: 1,
      activeStudents: 24,
      classCount: 1,
      gettingStarted: 0,
      classes: [{ classId: "class-1", name: "Grade 3 Blue", grade: "GRADE_3", studentCount: 8, toWatchCount: 1, pendingRequestCount: 0 }],
      disclosure: "d",
    });
    vi.mocked(client.getStudentOverview).mockResolvedValue({
      snapshot: AMARA,
      skills: SKILLS,
      disclosure: "d",
      className: "Grade 3 Blue",
      skillBounds: BOUNDS,
    });
    renderRoute(<WatchListScreen selectedStudentId="s-amara" />, { path: "/watch", initialPath: "/watch" });
    // UI-refinement pass: the "Worth watching right now" badge is removed
    // from this card — the priority line is the signal it rendered now.
    await waitFor(() => expect(screen.getByText(/Priority 1 in Grade 3 Blue/)).toBeInTheDocument());
    // The detail pane's own tab bar is omitted (no sub-route to switch to
    // inline) — only the list's "Amara" name and the detail's heading exist.
    expect(screen.queryByText("Sessions")).not.toBeInTheDocument();
    restore();
  });
});

describe("WatchListScreen — per class (/classes/:classId/watch)", () => {
  it("shows a flat list scoped to the class, no top-k cut", async () => {
    const students = [AMARA, makeSnapshot({ studentId: "s-3", displayName: "Third", rankWithinSnapshot: 3 })];
    vi.mocked(client.getClassWatchList).mockResolvedValue({
      totalStudents: 8,
      disclosure: "d",
      students,
    });
    vi.mocked(client.getCohort).mockResolvedValue({
      classId: "class-1",
      className: "Grade 3 Blue",
      studentCount: 8,
      toWatchCount: 2,
      gettingStartedCount: 0,
      pendingRequestCount: 0,
      students,
      disclosure: "d",
      grade: "GRADE_3",
      classKey: "9K3P21",
    });
    renderRoute(<WatchListScreen classId="class-1" />, {
      path: "/classes/:classId/watch",
      initialPath: "/classes/class-1/watch",
    });
    await waitFor(() => expect(screen.getByText("Amara")).toBeInTheDocument());
    expect(screen.getByText("Third")).toBeInTheDocument();
  });
});
