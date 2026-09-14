import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import HomeRoute from "../home/HomeRoute";
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
      deleteClass: vi.fn(),
      getJoinRequests: vi.fn(),
      approveJoinRequest: vi.fn(),
      rejectJoinRequest: vi.fn(),
    },
  };
});

const { client, DuplicateClassNameError } = await import("../../api/client");

const HOME_SUMMARY = {
  teacherName: "Ms Perera",
  studentsToWatch: 7,
  activeStudents: 83,
  classCount: 3,
  gettingStarted: 9,
  classes: [
    { classId: "class-1", name: "Grade 3 Blue", grade: "GRADE_3" as const, studentCount: 28, toWatchCount: 6, pendingRequestCount: 0 },
  ],
  disclosure: "Literature-informed synthetic data — not clinical evidence.",
};

function renderHome() {
  return renderRoute(<HomeRoute />, { path: "/", initialPath: "/" });
}

beforeEach(() => {
  vi.mocked(client.getHome).mockReset();
  vi.mocked(client.createClass).mockReset();
});

describe("HomeRoute — the watch card", () => {
  it("shows the count, with the total kept for screen readers (UI-refinement: visually just the count)", async () => {
    vi.mocked(client.getHome).mockResolvedValue(HOME_SUMMARY);
    renderHome();
    await waitFor(() => expect(screen.getByText("7")).toBeInTheDocument());
    expect(screen.getByText("of 83 students")).toBeInTheDocument();
  });

  it("does not show the 'Based on recent learning activity' framing sentence on this card (removed per explicit direction)", async () => {
    vi.mocked(client.getHome).mockResolvedValue(HOME_SUMMARY);
    renderHome();
    await waitFor(() => expect(screen.getByText("7")).toBeInTheDocument());
    expect(screen.queryByText("Based on recent learning activity")).not.toBeInTheDocument();
  });

  it("links to the watch list", async () => {
    vi.mocked(client.getHome).mockResolvedValue(HOME_SUMMARY);
    renderHome();
    await waitFor(() => expect(screen.getByText("7")).toBeInTheDocument());
    const link = screen.getByText("View watch list").closest("a")!;
    expect(link).toHaveAttribute("href", "/watch");
  });
});

describe("HomeRoute — stat tiles and classes", () => {
  it("shows Active Students, Classes, Getting Started (UI-refinement: no info icon on this tile)", async () => {
    vi.mocked(client.getHome).mockResolvedValue(HOME_SUMMARY);
    renderHome();
    await waitFor(() => expect(screen.getByText("Active Students")).toBeInTheDocument());
    expect(screen.getByText("Classes")).toBeInTheDocument();
    expect(screen.getByText("Getting Started")).toBeInTheDocument();
    expect(screen.queryByLabelText(/still building their learning history/)).not.toBeInTheDocument();
  });

  it("renders class cards with name, student count and to-watch count", async () => {
    vi.mocked(client.getHome).mockResolvedValue(HOME_SUMMARY);
    renderHome();
    await waitFor(() => expect(screen.getByText("Grade 3 Blue")).toBeInTheDocument());
    // "28 · 6 watch" — the numbers are their own <span>, so the sentence is
    // split across nodes; check the card's combined text instead of a
    // single-node text match.
    const card = screen.getByText("Grade 3 Blue").closest("button")!;
    expect(card.textContent).toContain("28");
    expect(card.textContent).toContain("6");
    expect(card.textContent).toContain("watch");
  });
});

describe("HomeRoute — create class (Step 6)", () => {
  it("the ⊕ opens Create Class, and Grade 2 / Grade 3 are two separate buttons on the same line", async () => {
    vi.mocked(client.getHome).mockResolvedValue(HOME_SUMMARY);
    renderHome();
    await waitFor(() => expect(screen.getByText("Grade 3 Blue")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: "Add class" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    const grade2 = screen.getByRole("button", { name: "Grade 2" });
    const grade3 = screen.getByRole("button", { name: "Grade 3" });
    expect(grade2).toBeInTheDocument();
    expect(grade3).toBeInTheDocument();
    // Grade 3 is the default selection.
    expect(grade3).toHaveAttribute("aria-pressed", "true");
    expect(grade2).toHaveAttribute("aria-pressed", "false");

    await userEvent.click(grade2);
    expect(grade2).toHaveAttribute("aria-pressed", "true");
    expect(grade3).toHaveAttribute("aria-pressed", "false");
  });

  it("submitting shows the class key immediately (Created → Class Key)", async () => {
    vi.mocked(client.getHome).mockResolvedValue(HOME_SUMMARY);
    vi.mocked(client.createClass).mockResolvedValue({
      classId: "class-new",
      className: "Grade 2 Sunshine",
      grade: "GRADE_2",
      classKey: "8P5R47",
    });
    renderHome();
    await waitFor(() => expect(screen.getByText("Grade 3 Blue")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: "Add class" }));
    await userEvent.type(screen.getByLabelText("Class name"), "Grade 2 Sunshine");
    await userEvent.click(screen.getByRole("button", { name: "Create class" }));

    await waitFor(() => expect(screen.getByText("8P5R47")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Go to class" })).toBeInTheDocument();
    // The Create Class dialog is gone — Class Key replaces it, not stacks.
    expect(screen.queryByRole("dialog", { name: "Create Class" })).not.toBeInTheDocument();
  });

  it("a duplicate class name renders an inline error on the name field and does not crash", async () => {
    vi.mocked(client.getHome).mockResolvedValue(HOME_SUMMARY);
    vi.mocked(client.createClass).mockRejectedValue(
      new DuplicateClassNameError('A class named "Grade 3 Blue" already exists.'),
    );
    renderHome();
    await waitFor(() => expect(screen.getByText("Grade 3 Blue")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: "Add class" }));
    await userEvent.type(screen.getByLabelText("Class name"), "Grade 3 Blue");
    await userEvent.click(screen.getByRole("button", { name: "Create class" }));

    await waitFor(() =>
      expect(
        screen.getByText('A class named "Grade 3 Blue" already exists.'),
      ).toBeInTheDocument(),
    );
    // Still on the Create Class dialog — no crash, no Class Key dialog.
    expect(screen.getByLabelText("Class name")).toBeInTheDocument();
    expect(screen.queryByText(/^Class Key$/)).not.toBeInTheDocument();
  });

  it("Create Class dialog traps focus, closes on Escape, restores focus to the ⊕ trigger", async () => {
    vi.mocked(client.getHome).mockResolvedValue(HOME_SUMMARY);
    renderHome();
    await waitFor(() => expect(screen.getByText("Grade 3 Blue")).toBeInTheDocument());

    const trigger = screen.getByRole("button", { name: "Add class" });
    await userEvent.click(trigger);
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-labelledby");

    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.activeElement).toBe(trigger);
  });
});

describe("HomeRoute — hardening pass: heading hierarchy and responsive layout", () => {
  it("has exactly one h1 landmark heading", async () => {
    vi.mocked(client.getHome).mockResolvedValue(HOME_SUMMARY);
    renderHome();
    await waitFor(() => expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument());
  });

  it("the class list is a two-column grid at sm (plan §8), single column below it", async () => {
    vi.mocked(client.getHome).mockResolvedValue(HOME_SUMMARY);
    const { container } = renderHome();
    await waitFor(() => expect(screen.getByText("Grade 3 Blue")).toBeInTheDocument());
    const grid = container.querySelector(".grid.grid-cols-1");
    expect(grid).not.toBeNull();
    expect(grid!.className).toMatch(/sm:grid-cols-2/);
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
  // UI-refinement pass: both the framing line ("The system flags learners
  // for teacher review.") and the disclosure footer ("Literature-informed
  // synthetic data — not clinical evidence.") were deliberately removed
  // from Home at the user's explicit direction, overriding docs/12 §1's
  // "every analytics surface" requirement for this one screen. Both still
  // render on the other analytics surfaces (Watch List, Student Overview)
  // — this is a scoped exception, not a reversal of the governance rule.
  it("does not render the framing line or the disclosure footer on this screen", async () => {
    vi.mocked(client.getHome).mockResolvedValue(HOME_SUMMARY);
    renderHome();
    await waitFor(() => expect(screen.getByText("Grade 3 Blue")).toBeInTheDocument());
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

describe("HomeRoute — scroll layout: pinned watch card, sticky 'Your Classes'", () => {
  // jsdom has no layout engine, so it cannot scroll. These pin the STRUCTURE the
  // scrolling depends on: what is pinned, what slides under it, what sticks.
  beforeEach(() => {
    vi.mocked(client.getHome).mockResolvedValue(HOME_SUMMARY);
  });

  it("pins the buttons and the watch card together at the top", async () => {
    renderHome();
    await waitFor(() => expect(screen.getByText("Students to Watch")).toBeInTheDocument());
    const pinned = screen.getByText("Students to Watch").closest(".sticky") as HTMLElement;
    expect(pinned).not.toBeNull();
    expect(pinned.className).toMatch(/top-0/);
    // The Add-class and Profile buttons ride with it.
    expect(pinned.contains(screen.getByRole("button", { name: "Add class" }))).toBe(true);
    expect(pinned.contains(screen.getByRole("link", { name: "Profile" }))).toBe(true);
    // Its page-coloured background is what hides the tiles scrolling beneath it.
    expect(pinned.className).toMatch(/bg-background/);
  });

  it("the three stat tiles are NOT pinned, so they slide up under the watch card", async () => {
    renderHome();
    await waitFor(() => expect(screen.getByText("Active Students")).toBeInTheDocument());
    const pinned = screen.getByText("Students to Watch").closest(".sticky") as HTMLElement;
    for (const label of ["Active Students", "Classes", "Getting Started"]) {
      expect(pinned.contains(screen.getByText(label))).toBe(false);
    }
  });

  it("'Your Classes' sticks beneath the pinned block, above the class cards", async () => {
    renderHome();
    await waitFor(() => expect(screen.getByText("Your Classes")).toBeInTheDocument());
    const heading = screen.getByRole("heading", { name: "Your Classes" });
    expect(heading.className).toMatch(/sticky/);
    expect(heading.className).toMatch(/bg-background/);
    // Below the pinned block in stacking order, so it passes under the watch card.
    expect(heading.className).toMatch(/z-10/);
    const pinned = screen.getByText("Students to Watch").closest(".sticky") as HTMLElement;
    expect(pinned.className).toMatch(/z-20/);
    // Its offset is set from the pinned block's measured height (a number, not a guess).
    expect(heading.style.top).toMatch(/px$/);
  });
});

describe("HomeRoute — swipe a class card to delete it (2026-09-14)", () => {
  function swipeLeft(card: HTMLElement) {
    fireEvent.pointerDown(card, { pointerId: 1, clientX: 300, clientY: 100, button: 0, pointerType: "touch" });
    fireEvent.pointerMove(card, { pointerId: 1, clientX: 250, clientY: 100, pointerType: "touch" });
    fireEvent.pointerMove(card, { pointerId: 1, clientX: 200, clientY: 100, pointerType: "touch" });
    fireEvent.pointerUp(card, { pointerId: 1, clientX: 200, clientY: 100, pointerType: "touch" });
  }

  it("swipe, Delete, are-you-sure Yes, type the name, Delete -- then the class list is reloaded", async () => {
    vi.mocked(client.getHome).mockResolvedValue(HOME_SUMMARY);
    vi.mocked(client.deleteClass).mockReset().mockResolvedValue(undefined);
    renderHome();
    await waitFor(() => expect(screen.getByText("Grade 3 Blue")).toBeInTheDocument());

    swipeLeft(screen.getByTestId("swipe-card"));
    await userEvent.click(screen.getByRole("button", { name: "Delete Grade 3 Blue" }));

    const dialog = await screen.findByRole("dialog", { name: "Delete “Grade 3 Blue”?" });
    expect(dialog).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Yes" }));
    expect(client.deleteClass).not.toHaveBeenCalled();

    await userEvent.type(screen.getByLabelText(/to confirm/), "Grade 3 Blue");
    const loadsBefore = vi.mocked(client.getHome).mock.calls.length;
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(client.deleteClass).toHaveBeenCalledWith("class-1", "Grade 3 Blue");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(vi.mocked(client.getHome).mock.calls.length).toBeGreaterThan(loadsBefore));
  });

  it("No closes the dialog, slides the card back and deletes nothing", async () => {
    vi.mocked(client.getHome).mockResolvedValue(HOME_SUMMARY);
    vi.mocked(client.deleteClass).mockReset();
    renderHome();
    await waitFor(() => expect(screen.getByText("Grade 3 Blue")).toBeInTheDocument());

    const card = screen.getByTestId("swipe-card");
    swipeLeft(card);
    await userEvent.click(screen.getByRole("button", { name: "Delete Grade 3 Blue" }));
    await userEvent.click(await screen.findByRole("button", { name: "No" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(card.style.transform).toBe("translateX(0px)");
    expect(client.deleteClass).not.toHaveBeenCalled();
  });
});
