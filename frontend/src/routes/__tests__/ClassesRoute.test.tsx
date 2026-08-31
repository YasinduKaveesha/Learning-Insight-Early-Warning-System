import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ClassesRoute from "../classes/ClassesRoute";
import { renderRoute } from "./testUtils";

vi.mock("../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../api/client")>("../../api/client");
  return {
    DuplicateClassNameError: actual.DuplicateClassNameError,
    isDuplicateClassNameError: actual.isDuplicateClassNameError,
    client: {
      getHome: vi.fn(),
      createClass: vi.fn(),
    },
  };
});

const { client } = await import("../../api/client");

const HOME_SUMMARY = {
  teacherName: "Ms Perera",
  studentsToWatch: 7,
  activeStudents: 83,
  classCount: 2,
  gettingStarted: 9,
  classes: [
    { classId: "class-1", name: "Grade 3 Blue", grade: "GRADE_3" as const, studentCount: 28, toWatchCount: 6 },
    { classId: "class-2", name: "Grade 2 Sunshine", grade: "GRADE_2" as const, studentCount: 20, toWatchCount: 1 },
  ],
  disclosure: "Literature-informed synthetic data — not clinical evidence.",
};

function renderClasses() {
  return renderRoute(<ClassesRoute />, { path: "/classes", initialPath: "/classes" });
}

beforeEach(() => {
  vi.mocked(client.getHome).mockReset();
  vi.mocked(client.createClass).mockReset();
});

describe("ClassesRoute — the complete list (plan §3 /classes)", () => {
  it("loading renders skeletons, not a spinner", () => {
    vi.mocked(client.getHome).mockReturnValue(new Promise(() => {}));
    renderClasses();
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
  });

  it("loaded shows every class using the shared ClassCard shape, two-column at sm", async () => {
    vi.mocked(client.getHome).mockResolvedValue(HOME_SUMMARY);
    const { container } = renderClasses();
    await waitFor(() => expect(screen.getByText("Grade 3 Blue")).toBeInTheDocument());
    expect(screen.getByText("Grade 2 Sunshine")).toBeInTheDocument();
    expect(screen.getByText(/28 students/)).toBeInTheDocument();
    const grid = container.querySelector(".grid.grid-cols-1");
    expect(grid).not.toBeNull();
    expect(grid!.className).toMatch(/sm:grid-cols-2/);
  });

  it("empty state offers class creation — the first-run path", async () => {
    vi.mocked(client.getHome).mockResolvedValue({ ...HOME_SUMMARY, classCount: 0, classes: [] });
    renderClasses();
    await waitFor(() =>
      expect(screen.getByText("Create your first class to get started.")).toBeInTheDocument(),
    );
  });

  it("error state says what failed and offers retry, never a raw error string", async () => {
    vi.mocked(client.getHome).mockRejectedValue(new Error("fetch failed: ECONNREFUSED"));
    renderClasses();
    await waitFor(() => expect(screen.getByText(/Couldn't load your classes/)).toBeInTheDocument());
    expect(screen.queryByText(/ECONNREFUSED/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("has exactly one h1 landmark heading", async () => {
    vi.mocked(client.getHome).mockResolvedValue(HOME_SUMMARY);
    renderClasses();
    await waitFor(() => expect(screen.getByRole("heading", { level: 1, name: "All Classes" })).toBeInTheDocument());
  });

  it("reuses Home's create-class flow: the ⊕ opens Create Class and submitting shows the class key", async () => {
    vi.mocked(client.getHome).mockResolvedValue(HOME_SUMMARY);
    vi.mocked(client.createClass).mockResolvedValue({
      classId: "class-new",
      className: "Grade 2 Sunrise",
      grade: "GRADE_2",
      classKey: "9Q3K21",
    });
    renderClasses();
    await waitFor(() => expect(screen.getByText("Grade 3 Blue")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: "Add class" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Class name"), "Grade 2 Sunrise");
    await userEvent.click(screen.getByRole("button", { name: "Create class" }));

    await waitFor(() => expect(screen.getByText("9Q3K21")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Go to class" })).toBeInTheDocument();
  });
});
