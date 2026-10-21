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
      expect(screen.getByText("No students yet. Share the class key so students can join.")).toBeInTheDocument(),
    );
  });

  it("an empty class still shows the three tiles, at zero, and prompts to add students", async () => {
    mockCohort([], { studentCount: 0, toWatchCount: 0, gettingStartedCount: 0, classKey: "4T7N26" });
    renderClassroom();
    await waitFor(() => expect(screen.getByText("Students")).toBeInTheDocument());
    expect(screen.getByText("To Watch")).toBeInTheDocument();
    expect(screen.getByText("Getting Started")).toBeInTheDocument();
    expect(screen.getAllByText("0")).toHaveLength(3);
    expect(screen.getByText("Add students")).toBeInTheDocument();
  });

  it("an empty class STILL shows the pending-requests banner", async () => {
    // The bug this pins: the banner used to live inside the "has students"
    // branch, so a brand-new class with its first join request showed a red
    // dot on Home and no way to reach the approve screen. Found for real on
    // 2026-09-14, the first time a child joined a class made in the dashboard.
    mockCohort([], { studentCount: 0, classKey: "4T7N26", pendingRequestCount: 1 });
    renderClassroom();
    await waitFor(() => expect(screen.getByText(/1 join request pending/)).toBeInTheDocument());
    expect(screen.getByText(/1 join request pending/).closest("a")).toHaveAttribute(
      "href",
      "/classes/class-1/requests",
    );
  });

  it("an empty class does not show roster sections that could only be empty", async () => {
    mockCohort([], { studentCount: 0, classKey: "4T7N26" });
    renderClassroom();
    await waitFor(() => expect(screen.getByText("Students")).toBeInTheDocument());
    expect(screen.queryByText("Students to Watch")).not.toBeInTheDocument();
    expect(screen.queryByText("All Students")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Search students")).not.toBeInTheDocument();
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
    // UI-refinement pass: back now goes to Home, labelled "Home".
    const backLink = screen.getByRole("link", { name: "Home" });
    expect(backLink).toBeInTheDocument();
    expect(backLink).toHaveAttribute("href", "/");
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

    // UI-refinement pass: StudentCard no longer shows a watch-status
    // badge — Kavya's trajectory word ("Stable", from her fixture) is
    // still visible on her card, preserved through the filter.
    expect(screen.getByText("Stable")).toBeInTheDocument();
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
    // UI-refinement pass: no watch-status badge on this card any more —
    // the Getting Started state still renders as its own first-class line
    // ("N of 3 sessions"), not an error or empty state.
    expect(within(card).getByText("1 of 3 sessions")).toBeInTheDocument();
  });
});

describe("ClassroomRoute — framing, disclosure, and forbidden vocabulary", () => {
  // UI-refinement pass: both the framing line and the disclosure footer
  // were removed from this screen at explicit direction (the same scoped
  // exception as Home).
  it("does not render the framing line or the disclosure footer", async () => {
    mockCohort(ORDERED_COHORT);
    renderClassroom();
    await waitFor(() => expect(screen.getByText("Amara")).toBeInTheDocument());
    expect(screen.queryByText("The system flags learners for teacher review.")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Literature-informed synthetic data — not clinical evidence."),
    ).not.toBeInTheDocument();
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

describe("ClassroomRoute — decision B: a handled suggestion moves the card, not the count", () => {
  const HANDLED = makeSnapshot({
    studentId: "s-handled",
    displayName: "Dilshan",
    watchFlag: true,
    suggestionStatus: "accepted",
  });

  function sectionOf(name: string) {
    // The card's nearest <section> tells us which list it is in.
    return screen.getByText(name).closest("section")!.querySelector("h2, h3")?.textContent ?? "";
  }

  it("moves a handled learner from Students to Watch to All Students", async () => {
    mockCohort([WATCHED_1, HANDLED, NO_CONCERN], { handledCount: 1 });
    renderClassroom();
    await waitFor(() => expect(screen.getByText("Dilshan")).toBeInTheDocument());

    expect(sectionOf("Amara")).toMatch(/Students to Watch/);
    expect(sectionOf("Dilshan")).toMatch(/All Students/);
  });

  it("keeps the blue watching tint and says why it is there", async () => {
    mockCohort([WATCHED_1, HANDLED], { handledCount: 1 });
    renderClassroom();
    await waitFor(() => expect(screen.getByText("Dilshan")).toBeInTheDocument());

    expect(screen.getByText("Suggestion accepted")).toBeInTheDocument();
    const card = screen.getByText("Dilshan").closest("a")!.firstElementChild as HTMLElement;
    expect(card.className).toMatch(/toneCard-blue/);
  });

  it("leads All Students, ahead of learners with no concern", async () => {
    mockCohort([NO_CONCERN, HANDLED], { handledCount: 1 });
    renderClassroom();
    await waitFor(() => expect(screen.getByText("Dilshan")).toBeInTheDocument());

    const names = Array.from(
      screen.getByText("Dilshan").closest("section")!.querySelectorAll("a"),
    ).map((a) => a.textContent ?? "");
    expect(names[0]).toContain("Dilshan");
    expect(names[1]).toContain("Kavya");
  });

  it("the To Watch tile shows the deducted count, with no 'handled' caption (D50)", async () => {
    // The client has already subtracted handled learners from toWatchCount; the
    // tile shows that number as-is and says nothing about how it was reached.
    mockCohort([WATCHED_1, HANDLED], { toWatchCount: 1, handledCount: 1 });
    renderClassroom();
    await waitFor(() => expect(screen.getByText("Dilshan")).toBeInTheDocument());
    const tile = screen.getByText("To Watch").closest("div")!.parentElement!;
    expect(tile.textContent).toContain("1");
    expect(screen.queryByText(/handled/i)).not.toBeInTheDocument();
  });

  it("a modified suggestion reads differently from an accepted one", async () => {
    mockCohort([{ ...HANDLED, suggestionStatus: "modified" }], { handledCount: 1 });
    renderClassroom();
    await waitFor(() => expect(screen.getByText("Suggestion changed")).toBeInTheDocument());
  });
});

describe("ClassroomRoute — scroll layout: pinned top bar, sticky section titles", () => {
  // jsdom cannot scroll; these pin the structure the scrolling depends on.

  it("pins the top bar and the search box together", async () => {
    mockCohort(ORDERED_COHORT);
    renderClassroom();
    await waitFor(() => expect(screen.getByText("Amara")).toBeInTheDocument());
    const pinned = screen.getByRole("link", { name: "Home" }).closest(".sticky") as HTMLElement;
    expect(pinned).not.toBeNull();
    expect(pinned.className).toMatch(/top-0/);
    expect(pinned.className).toMatch(/z-20/);
    expect(pinned.contains(screen.getByLabelText("Search students"))).toBe(true);
  });

  it("the three tiles and the join-requests banner are pinned too — only the student cards scroll", async () => {
    // On the CLASS page the tiles stay still (explicit direction, 2026-09-14).
    // Home differs on purpose: there the tiles slide under the watch card.
    mockCohort(ORDERED_COHORT, { pendingRequestCount: 1 });
    renderClassroom();
    await waitFor(() => expect(screen.getByText("Amara")).toBeInTheDocument());
    const pinned = screen.getByRole("link", { name: "Home" }).closest(".sticky") as HTMLElement;
    for (const label of ["Students", "To Watch", "Getting Started"]) {
      expect(pinned.contains(screen.getByText(label))).toBe(true);
    }
    expect(pinned.contains(screen.getByText(/1 join request pending/))).toBe(true);
    // ...and no student card is in it.
    expect(pinned.contains(screen.getByText("Amara"))).toBe(false);
  });

  it("each section title sticks beneath the pinned block, so only the cards scroll", async () => {
    mockCohort(ORDERED_COHORT);
    renderClassroom();
    await waitFor(() => expect(screen.getByText("Amara")).toBeInTheDocument());
    for (const title of ["Students to Watch", "All Students"]) {
      const holder = screen.getByText(title).closest(".sticky") as HTMLElement;
      expect(holder).not.toBeNull();
      expect(holder.className).toMatch(/z-10/);
      expect(holder.className).toMatch(/bg-background/);
      // Set from the pinned block's measured height, not a hard-coded guess.
      expect(holder.style.top).toMatch(/px$/);
      // A card is NOT inside the sticky title, so the cards are what scroll.
      expect(holder.contains(screen.getByText("Amara"))).toBe(false);
    }
  });

  it("an empty class pins only the top bar -- no search box to pin", async () => {
    mockCohort([], { studentCount: 0, classKey: "4T7N26" });
    renderClassroom();
    await waitFor(() => expect(screen.getByText(/No students yet/)).toBeInTheDocument());
    expect(screen.queryByLabelText("Search students")).not.toBeInTheDocument();
  });
});
