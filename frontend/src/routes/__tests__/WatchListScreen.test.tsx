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
        { classId: "class-1", name: "Grade 3 Blue", grade: "GRADE_3", studentCount: 8, toWatchCount: 1 },
        { classId: "class-2", name: "Grade 3 Green", grade: "GRADE_3", studentCount: 8, toWatchCount: 1 },
      ],
      disclosure: "Literature-informed synthetic data — not clinical evidence.",
    });
    renderRoute(<WatchListScreen />, { path: "/watch", initialPath: "/watch" });

    await waitFor(() => expect(screen.getByText("Amara")).toBeInTheDocument());
    expect(screen.getByText("2 of 24 students")).toBeInTheDocument();
    // Grouped by class — both class-name headings render.
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
      classes: [{ classId: "class-1", name: "Grade 3 Blue", grade: "GRADE_3", studentCount: 8, toWatchCount: 1 }],
      disclosure: "d",
    });
    renderRoute(<WatchListScreen />, { path: "/watch", initialPath: "/watch" });
    await waitFor(() => expect(screen.getByText("Amara")).toBeInTheDocument());
    expect(
      screen.getByText("Subtraction has not improved across the last four sessions."),
    ).toBeInTheDocument();
  });

  it("a 'Priority N' badge appears here, and nowhere outside a watch list", async () => {
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
      classes: [{ classId: "class-1", name: "Grade 3 Blue", grade: "GRADE_3", studentCount: 8, toWatchCount: 1 }],
      disclosure: "d",
    });
    renderRoute(<WatchListScreen />, { path: "/watch", initialPath: "/watch" });
    await waitFor(() => expect(screen.getByText(/Priority 1/)).toBeInTheDocument());
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

describe("WatchListScreen — per class (/classes/:classId/watch)", () => {
  it("shows a flat list scoped to the class, no top-k cut", async () => {
    const students = [AMARA, makeSnapshot({ studentId: "s-3", displayName: "Third", rankWithinSnapshot: 3 })];
    vi.mocked(client.getClassWatchList).mockResolvedValue({
      totalStudents: 8,
      disclosure: "d",
      students,
    });
    renderRoute(<WatchListScreen classId="class-1" />, {
      path: "/classes/:classId/watch",
      initialPath: "/classes/class-1/watch",
    });
    await waitFor(() => expect(screen.getByText("Amara")).toBeInTheDocument());
    expect(screen.getByText("Third")).toBeInTheDocument();
    expect(screen.getByText("2 of 8 students")).toBeInTheDocument();
  });
});
