import { QueryClient } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/client", () => ({
  client: {
    getCohort: vi.fn(),
    getClassStudentOverviews: vi.fn(),
  },
}));

const { client } = await import("../../api/client");
const { prefetchClasses, prefetchClassStudents, seedStudents } = await import("../prefetch");

function student(id: string, recName = "rec") {
  return {
    studentId: id,
    overview: { snapshot: { studentId: id } } as never,
    recommendations: [{ recommendationId: `${recName}-${id}` }] as never,
  };
}

let queryClient: QueryClient;

beforeEach(() => {
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 60_000 } } });
  vi.mocked(client.getCohort).mockReset().mockResolvedValue({ classId: "c" } as never);
  vi.mocked(client.getClassStudentOverviews).mockReset().mockResolvedValue([]);
});

describe("seedStudents", () => {
  it("puts each learner under the keys the student screen reads", () => {
    seedStudents(queryClient, [student("s1")]);
    expect(queryClient.getQueryData(["studentOverview", "s1"])).toEqual({ snapshot: { studentId: "s1" } });
    expect(queryClient.getQueryData(["studentRecommendations", "s1"])).toEqual([{ recommendationId: "rec-s1" }]);
  });

  it("never overwrites data already in the cache, which may be fresher (a decision refetches it)", () => {
    queryClient.setQueryData(["studentRecommendations", "s1"], [{ recommendationId: "fresh-s1" }]);
    seedStudents(queryClient, [student("s1", "stale")]);
    expect(queryClient.getQueryData(["studentRecommendations", "s1"])).toEqual([{ recommendationId: "fresh-s1" }]);
  });
});

describe("prefetchClassStudents", () => {
  it("fetches a class once and serves the second call from the cache", async () => {
    vi.mocked(client.getClassStudentOverviews).mockResolvedValue([student("s1")]);
    await prefetchClassStudents(queryClient, "c1");
    await prefetchClassStudents(queryClient, "c1");
    expect(client.getClassStudentOverviews).toHaveBeenCalledTimes(1);
    expect(queryClient.getQueryData(["studentOverview", "s1"])).toBeDefined();
  });

  it("swallows a failure -- the page loads on its own when opened", async () => {
    vi.mocked(client.getClassStudentOverviews).mockRejectedValue(new Error("HTTP 503"));
    // Resolves to the learner ids (empty here) rather than throwing: the queue
    // uses them to line up each learner's session history.
    await expect(prefetchClassStudents(queryClient, "c1")).resolves.toEqual([]);
    expect(queryClient.getQueryData(["studentOverview", "s1"])).toBeUndefined();
  });
});

describe("prefetchClasses", () => {
  it("warms every class page and every class's learners", async () => {
    await prefetchClasses(queryClient, ["c1", "c2", "c3"]);
    expect(vi.mocked(client.getCohort).mock.calls.map((c) => c[0]).sort()).toEqual(["c1", "c2", "c3"]);
    expect(vi.mocked(client.getClassStudentOverviews).mock.calls.map((c) => c[0]).sort()).toEqual([
      "c1",
      "c2",
      "c3",
    ]);
    expect(queryClient.getQueryData(["cohort", "c2"])).toEqual({ classId: "c" });
  });

  it("warms one class at a time, so background work never crowds the page on screen", async () => {
    let inFlight = 0;
    let peak = 0;
    vi.mocked(client.getCohort).mockImplementation(async () => {
      inFlight += 1;
      peak = Math.max(peak, inFlight);
      await new Promise((r) => setTimeout(r, 10));
      inFlight -= 1;
      return { classId: "c" } as never;
    });
    await prefetchClasses(queryClient, ["c1", "c2", "c3", "c4", "c5"]);
    expect(peak).toBe(1);
  });

  it("does nothing for no classes", async () => {
    await prefetchClasses(queryClient, []);
    expect(client.getCohort).not.toHaveBeenCalled();
  });
});
