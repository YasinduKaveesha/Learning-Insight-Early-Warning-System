import { screen, waitFor } from "@testing-library/react";
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
    { classId: "class-1", name: "Grade 3 Blue", grade: "GRADE_3" as const, studentCount: 28, toWatchCount: 6 },
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

describe("HomeRoute — create class (Step 6)", () => {
  it("the ⊕ opens Create Class, and the grade select offers exactly Grade 2 and Grade 3", async () => {
    vi.mocked(client.getHome).mockResolvedValue(HOME_SUMMARY);
    renderHome();
    await waitFor(() => expect(screen.getByText("Grade 3 Blue")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: "Add class" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    const options = screen.getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["Grade 2", "Grade 3"]);
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
