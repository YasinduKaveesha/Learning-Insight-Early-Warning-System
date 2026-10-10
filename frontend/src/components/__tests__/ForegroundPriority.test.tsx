import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, Link } from "react-router-dom";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/client", () => ({
  client: {
    getHome: vi.fn(),
    getCohort: vi.fn(),
    getClassWatchList: vi.fn(),
    getWatchList: vi.fn(),
    getClassStudentOverviews: vi.fn(),
    getStudentSessions: vi.fn(),
  },
}));

const { client } = await import("../../api/client");
const { ForegroundPriority } = await import("../shared/ForegroundPriority");
const { classIdFromPath } = await import("../../lib/classPath");
const { cancelBackgroundLoad, isBackgroundPaused, startBackgroundLoad } = await import(
  "../../lib/prefetch"
);

let calls: string[] = [];
let queryClient: QueryClient;

const HOME = {
  teacherName: "Ms Perera",
  studentsToWatch: 1,
  activeStudents: 2,
  classCount: 2,
  gettingStarted: 0,
  classes: [
    { classId: "c1", name: "A", grade: "GRADE_2", studentCount: 10, toWatchCount: 1 },
    { classId: "c2", name: "B", grade: "GRADE_3", studentCount: 10, toWatchCount: 5 },
  ],
  disclosure: "d",
};

/** A screen whose own query is slow, so "the background waited" is observable. */
function Screen({ name }: { name: string }) {
  const { data } = useQuery({
    queryKey: ["screen", name],
    queryFn: async () => {
      calls.push(`screen:${name}`);
      await new Promise((r) => setTimeout(r, 20));
      return name;
    },
  });
  return (
    <div>
      <p>{data ?? "loading"}</p>
      <Link to="/other">go</Link>
    </div>
  );
}

function renderAt(path: string) {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <ForegroundPriority />
        <Routes>
          <Route path="/deep" element={<Screen name="deep" />} />
          <Route path="/other" element={<Screen name="other" />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  calls = [];
  cancelBackgroundLoad();
  queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 60_000 } },
  });
  vi.mocked(client.getHome).mockReset().mockImplementation(async () => {
    calls.push("home");
    return HOME as never;
  });
  vi.mocked(client.getWatchList).mockReset().mockImplementation(async () => {
    calls.push("watch");
    return [] as never;
  });
  vi.mocked(client.getCohort).mockReset().mockImplementation(async (id: string) => {
    calls.push(`cohort:${id}`);
    return { classId: id } as never;
  });
  vi.mocked(client.getClassWatchList).mockReset().mockImplementation(async (id: string) => {
    calls.push(`classWatch:${id}`);
    return [] as never;
  });
  vi.mocked(client.getClassStudentOverviews).mockReset().mockImplementation(async (id: string) => {
    calls.push(`students:${id}`);
    return [] as never;
  });
});

afterEach(() => cancelBackgroundLoad());

describe("ForegroundPriority — the open screen loads before the warm-up", () => {
  it("plans a warm-up even when the teacher reloaded on a deep link, never having mounted Home", async () => {
    renderAt("/deep");
    await waitFor(() => expect(screen.getByText("deep")).toBeInTheDocument());
    // Before this component existed, only Home planned the warm-up, so a
    // reload here warmed nothing for the rest of the session.
    await waitFor(() => expect(calls).toContain("home"), { timeout: 2000 });
    await waitFor(() => expect(calls).toContain("cohort:c1"), { timeout: 2000 });
  });

  it("loads that screen's own data FIRST", async () => {
    renderAt("/deep");
    await waitFor(() => expect(calls).toContain("cohort:c1"), { timeout: 2000 });
    expect(calls.indexOf("screen:deep")).toBeLessThan(calls.indexOf("cohort:c1"));
  });

  it("holds the warm-up the moment the route changes", async () => {
    startBackgroundLoad(queryClient, ["c1", "c2"]);
    renderAt("/deep");
    // The hold is applied on mount/navigation, before the new screen's
    // queries have even started.
    expect(isBackgroundPaused()).toBe(true);
  });

  it("navigating to another screen holds it again, and that screen loads first", async () => {
    renderAt("/deep");
    await waitFor(() => expect(calls).toContain("cohort:c1"), { timeout: 2000 });
    const beforeNav = calls.length;

    await userEvent.setup().click(screen.getByRole("link", { name: "go" }));

    await waitFor(() => expect(screen.getByText("other")).toBeInTheDocument());
    const afterNav = calls.slice(beforeNav);
    // The new screen's own fetch is the first thing that happened after the
    // navigation -- the warm-up did not get a request in ahead of it.
    expect(afterNav[0]).toBe("screen:other");
  });

  it("lets the warm-up continue once the screen is idle", async () => {
    renderAt("/deep");
    await waitFor(() => expect(screen.getByText("deep")).toBeInTheDocument());
    await waitFor(() => expect(isBackgroundPaused()).toBe(false), { timeout: 2000 });
    await waitFor(() => expect(calls).toContain("cohort:c2"), { timeout: 3000 });
  });

  // EVERY protected route, not the two that happened to be wired by hand.
  // These are the real paths from App.tsx; the component names none of them.
  const EVERY_PROTECTED_PATH = [
    "/",
    "/watch",
    "/watch/s1",
    "/profile",
    "/classes/c1",
    "/classes/c1/watch",
    "/classes/c1/watch/s1",
    "/classes/c1/requests",
    "/classes/c1/reports",
    "/students/s1",
    "/students/s1/sessions",
  ];

  it.each(EVERY_PROTECTED_PATH)("holds the warm-up on %s", (path) => {
    startBackgroundLoad(queryClient, ["c1", "c2"]);
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[path]}>
          <ForegroundPriority />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(isBackgroundPaused()).toBe(true);
  });

  it("plans once, not once per navigation", async () => {
    renderAt("/deep");
    await waitFor(() => expect(calls).toContain("cohort:c1"), { timeout: 2000 });
    await userEvent.setup().click(screen.getByRole("link", { name: "go" }));
    await waitFor(() => expect(screen.getByText("other")).toBeInTheDocument());

    expect(calls.filter((c) => c === "home")).toHaveLength(1);
  });
});

describe("classIdFromPath — which class a screen is about", () => {
  it("finds the class on every class-scoped screen, not just the class page", () => {
    expect(classIdFromPath("/classes/c1")).toBe("c1");
    expect(classIdFromPath("/classes/c1/watch")).toBe("c1");
    expect(classIdFromPath("/classes/c1/watch/s1")).toBe("c1");
    expect(classIdFromPath("/classes/c1/requests")).toBe("c1");
    expect(classIdFromPath("/classes/c1/reports")).toBe("c1");
  });

  it("is null on screens that belong to no one class", () => {
    expect(classIdFromPath("/")).toBeNull();
    expect(classIdFromPath("/watch")).toBeNull();
    expect(classIdFromPath("/profile")).toBeNull();
    expect(classIdFromPath("/students/s1/sessions")).toBeNull();
    expect(classIdFromPath("/classes")).toBeNull();
  });
});
