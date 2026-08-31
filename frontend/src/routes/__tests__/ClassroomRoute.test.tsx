import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { LearnerSnapshot } from "../../lib/presentation";
import ClassroomRoute from "../classroom/ClassroomRoute";
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
    },
  };
});

const { client } = await import("../../api/client");

function makeSnapshot(overrides: Partial<LearnerSnapshot>): LearnerSnapshot {
  return {
    studentId: "id-" + Math.random(),
    displayName: "Student",
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
    ...overrides,
  };
}

const WATCHED_2 = makeSnapshot({
  studentId: "s-watched-2",
  displayName: "Priya",
  watchFlag: true,
  rankWithinSnapshot: 2,
  explanation: "Subtraction has not improved across the last four sessions.",
});
const WATCHED_1 = makeSnapshot({
  studentId: "s-watched-1",
  displayName: "Amara",
  watchFlag: true,
  rankWithinSnapshot: 1,
  explanation: "Place value has not improved across the last four sessions.",
});
const NO_CONCERN = makeSnapshot({ studentId: "s-calm", displayName: "Kavya", watchFlag: false });
const GETTING_STARTED = makeSnapshot({
  studentId: "s-gs",
  displayName: "Nimal",
  evidenceStatus: "insufficient_exposure",
  sessionsCompleted: 1,
  practiceTrajectory: { source: "practice_accuracy", state: "unknown" },
});

// Deliberately NOT pre-sorted by test-author intent — the route trusts and
// splits whatever order the API returned (already sorted by the mock
// client), so the fixture here mirrors that: watched-by-priority first,
// then no-concern, then Getting Started last.
const ORDERED_COHORT = [WATCHED_1, WATCHED_2, NO_CONCERN, GETTING_STARTED];

function mockCohort(students: LearnerSnapshot[], overrides: Partial<Record<string, unknown>> = {}) {
  vi.mocked(client.getCohort).mockResolvedValue({
    classId: "class-1",
    className: "Grade 3 Blue",
    grade: "GRADE_3",
    classKey: "7K4P92",
    studentCount: students.length,
    toWatchCount: students.filter((s) => s.watchFlag).length,
    gettingStartedCount: students.filter((s) => s.evidenceStatus !== "sufficient_evidence").length,
    pendingRequestCount: 0,
    students,
    disclosure: "Literature-informed synthetic data — not clinical evidence.",
    ...overrides,
  });
}

function renderClassroom() {
  return renderRoute(<ClassroomRoute />, {
    path: "/classes/:classId",
    initialPath: "/classes/class-1",
  });
}

beforeEach(() => {
  vi.mocked(client.getCohort).mockReset();
});

describe("ClassroomRoute — ordering", () => {
  it("orders watched students by priority, then no-concern, then Getting Started last", async () => {
    mockCohort(ORDERED_COHORT);
    renderClassroom();
    await waitFor(() => expect(screen.getByText("Amara")).toBeInTheDocument());

    const names = screen.getAllByText(/^(Amara|Priya|Kavya|Nimal)$/).map((el) => el.textContent);
    expect(names).toEqual(["Amara", "Priya", "Kavya", "Nimal"]);
  });

  it("a Getting Started student never sorts among the no-concern students — it is in a separate section", async () => {
    mockCohort(ORDERED_COHORT);
    renderClassroom();
    await waitFor(() => expect(screen.getByText("Nimal")).toBeInTheDocument());

    const watchSection = screen.getByText("Students to Watch").closest("section")!;
    const allSection = screen.getByText("All Students").closest("section")!;
    expect(within(watchSection).queryByText("Nimal")).not.toBeInTheDocument();
    expect(within(allSection).queryByText("Nimal")).toBeInTheDocument();
    expect(within(allSection).queryByText("Kavya")).toBeInTheDocument();

    // Kavya (no-concern) appears before Nimal (Getting Started) in the
    // "All Students" section — Getting Started sorts last, never merged in.
    const allText = allSection.textContent!;
    expect(allText.indexOf("Kavya")).toBeLessThan(allText.indexOf("Nimal"));
  });
});

describe("ClassroomRoute — the Step 6 ordering-defect fix", () => {
  // MIS_ORDERED_COHORT is exactly what a real backend that sorted by, say,
  // enrolment date might return: Getting Started FIRST, interleaved with
  // no-concern students, watched students not even grouped together. If
  // this screen still trusted the API's order (the Step 5 bug), the
  // rendered sections would reproduce this wrong order. sortCohortOrder is
  // now applied in ClassroomRoute itself, so the render must be correct
  // regardless of what mockCohort hands it — that's the whole point of
  // this test; without it the fix is unverified.
  const MIS_ORDERED_COHORT = [GETTING_STARTED, NO_CONCERN, WATCHED_2, WATCHED_1];

  it("still renders watched → no-concern → Getting Started last from a deliberately mis-ordered API response", async () => {
    mockCohort(MIS_ORDERED_COHORT);
    renderClassroom();
    await waitFor(() => expect(screen.getByText("Amara")).toBeInTheDocument());

    const names = screen.getAllByText(/^(Amara|Priya|Kavya|Nimal)$/).map((el) => el.textContent);
    expect(names).toEqual(["Amara", "Priya", "Kavya", "Nimal"]);

    const watchSection = screen.getByText("Students to Watch").closest("section")!;
    const allSection = screen.getByText("All Students").closest("section")!;
    expect(within(watchSection).queryByText("Nimal")).not.toBeInTheDocument();
    expect(within(allSection).getByText("Nimal")).toBeInTheDocument();
    expect(within(allSection).getByText("Kavya")).toBeInTheDocument();
    const allText = allSection.textContent!;
    expect(allText.indexOf("Kavya")).toBeLessThan(allText.indexOf("Nimal"));
  });
});

describe("ClassroomRoute — Class Info dialog (Step 6)", () => {
  it("the ⓘ opens a dialog showing the same key the cohort response carries", async () => {
    mockCohort(ORDERED_COHORT, { classKey: "9M3R58" });
    renderClassroom();
    await waitFor(() => expect(screen.getByText("Amara")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: "Class info" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("9M3R58")).toBeInTheDocument();
    expect(dialog).toHaveAttribute("aria-labelledby");
  });

  it("closes on Escape and restores focus to the ⓘ trigger", async () => {
    mockCohort(ORDERED_COHORT);
    renderClassroom();
    await waitFor(() => expect(screen.getByText("Amara")).toBeInTheDocument());

    const trigger = screen.getByRole("button", { name: "Class info" });
    await userEvent.click(trigger);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.activeElement).toBe(trigger);
  });
});

describe("ClassroomRoute — pending requests banner links to the requests screen", () => {
  it("shows the banner as a link to /classes/:classId/requests when there are pending requests", async () => {
    mockCohort(ORDERED_COHORT, { pendingRequestCount: 2 });
    renderClassroom();
    await waitFor(() => expect(screen.getByText(/2 join requests pending/)).toBeInTheDocument());
    const link = screen.getByText(/2 join requests pending/).closest("a")!;
    expect(link).toHaveAttribute("href", "/classes/class-1/requests");
  });
});

describe("ClassroomRoute — empty cohort shows the class key", () => {
  it("shows the class key as the useful empty state when the class has no students at all", async () => {
    mockCohort([], { studentCount: 0, classKey: "4T7N26" });
    renderClassroom();
    await waitFor(() =>
      expect(screen.getByText("No students yet. Share the key 4T7N26.")).toBeInTheDocument(),
    );
  });
});

describe("ClassroomRoute — hardening pass: heading hierarchy", () => {
  it("the class name is a real h1, reachable by assistive tech (not hidden inside an aria-label)", async () => {
    // Regression test for a real bug: the back link's aria-label used to
    // override its own visible text, so a screen reader heard only "Back
    // to classes" — the class name inside it was completely inaccessible.
    mockCohort(ORDERED_COHORT);
    renderClassroom();
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 1, name: "Grade 3 Blue" })).toBeInTheDocument(),
    );
    // The back link's accessible name no longer swallows the class name.
    expect(screen.getByRole("link", { name: "Back to classes" })).toBeInTheDocument();
  });
});

describe("ClassroomRoute — search", () => {
  it("filters both sections live on name and preserves each result's status", async () => {
    mockCohort(ORDERED_COHORT);
    renderClassroom();
    await waitFor(() => expect(screen.getByText("Amara")).toBeInTheDocument());

    const search = screen.getByLabelText("Search students");
    await userEvent.type(search, "ka");

    // "Kavya" matches; "Amara"/"Priya"/"Nimal" should be filtered out.
    expect(screen.getByText("Kavya")).toBeInTheDocument();
    expect(screen.queryByText("Amara")).not.toBeInTheDocument();
    expect(screen.queryByText("Priya")).not.toBeInTheDocument();
    expect(screen.queryByText("Nimal")).not.toBeInTheDocument();

    // Kavya's status (No current concern) is preserved through the filter.
    expect(screen.getByText("No current concern identified")).toBeInTheDocument();
  });
});

describe("ClassroomRoute — four states", () => {
  it("renders a loading skeleton before data arrives", () => {
    vi.mocked(client.getCohort).mockReturnValue(new Promise(() => {}));
    renderClassroom();
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
  });

  it("renders an empty state message for a section with no students", async () => {
    mockCohort([NO_CONCERN]);
    renderClassroom();
    await waitFor(() =>
      expect(
        screen.getByText("No students in this class are currently flagged for review."),
      ).toBeInTheDocument(),
    );
  });

  it("renders an error state with retry, never a raw error string", async () => {
    vi.mocked(client.getCohort).mockRejectedValue(new Error("Network request failed: 500"));
    renderClassroom();
    await waitFor(() => expect(screen.getByText(/Couldn't load this class/)).toBeInTheDocument());
    expect(screen.queryByText(/500/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("renders the Getting Started state as a first-class card, not an error or empty state", async () => {
    mockCohort([GETTING_STARTED]);
    renderClassroom();
    await waitFor(() => expect(screen.getByText("Nimal")).toBeInTheDocument());
    const card = screen.getByText("Nimal").closest("a")!;
    expect(within(card).getByText("Getting Started")).toBeInTheDocument();
  });
});

describe("ClassroomRoute — framing, disclosure, and forbidden vocabulary", () => {
  it("renders the framing line and the API-sourced disclosure", async () => {
    mockCohort(ORDERED_COHORT);
    renderClassroom();
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
    "risk score",
    "confidence",
  ];

  it("renders no banned vocabulary, probability, or score in the loaded state", async () => {
    mockCohort(ORDERED_COHORT);
    const { container } = renderClassroom();
    await waitFor(() => expect(screen.getByText("Amara")).toBeInTheDocument());
    const text = container.textContent!.toLowerCase();
    for (const term of FORBIDDEN) expect(text).not.toContain(term);
    expect(text).not.toMatch(/\d+%\s*confidence/);
  });

  it("renders no banned vocabulary in the error state", async () => {
    vi.mocked(client.getCohort).mockRejectedValue(new Error("boom"));
    const { container } = renderClassroom();
    await waitFor(() => expect(screen.getByText(/Couldn't load this class/)).toBeInTheDocument());
    const text = container.textContent!.toLowerCase();
    for (const term of FORBIDDEN) expect(text).not.toContain(term);
  });
});
