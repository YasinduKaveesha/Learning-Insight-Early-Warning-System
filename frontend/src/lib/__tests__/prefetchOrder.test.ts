import { QueryClient } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/client", () => ({
  client: {
    getCohort: vi.fn(),
    getClassWatchList: vi.fn(),
    getWatchList: vi.fn(),
    getClassStudentOverviews: vi.fn(),
    getStudentSessions: vi.fn(),
  },
}));

const { client } = await import("../../api/client");
const {
  NAVIGATION_HOLD,
  startBackgroundLoad,
  prioritiseClass,
  cancelBackgroundLoad,
  isBackgroundLoading,
  isBackgroundPaused,
  pauseBackgroundLoad,
  resumeBackgroundLoad,
  focusClass,
} = await import("../prefetch");

/**
 * THE ORDER IS THE CONTRACT. These tests record a transcript of every call the
 * warm-up makes, in the order it makes them, and assert on the shape of that
 * transcript -- not on counts, which would pass for any ordering at all.
 */
let calls: string[] = [];
let queryClient: QueryClient;

function overviewsFor(classId: string, n: number) {
  return Array.from({ length: n }, (_, i) => ({
    studentId: `${classId}-s${i + 1}`,
    overview: { snapshot: { studentId: `${classId}-s${i + 1}` } } as never,
    recommendations: [] as never,
  }));
}

/** Let the queue drain. Each task awaits a resolved promise or two, so a
 * handful of macrotask turns is plenty for these small plans. */
async function settle() {
  for (let i = 0; i < 400 && isBackgroundLoading(); i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

beforeEach(() => {
  calls = [];
  queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 60_000 } },
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
  vi.mocked(client.getClassStudentOverviews)
    .mockReset()
    .mockImplementation(async (id: string) => {
      calls.push(`students:${id}`);
      return overviewsFor(id, 2) as never;
    });
  vi.mocked(client.getStudentSessions).mockReset().mockImplementation(async (id: string) => {
    calls.push(`sessions:${id}`);
    return [] as never;
  });
});

afterEach(() => cancelBackgroundLoad());

describe("warm-up order: every class page, then every learner, then every session", () => {
  it("fetches all three class pages before any learner, and all learners before any session", async () => {
    startBackgroundLoad(queryClient, ["c1", "c2", "c3"]);
    await settle();

    const lastClassPage = Math.max(...["c1", "c2", "c3"].map((c) => calls.indexOf(`cohort:${c}`)));
    const firstLearnerFetch = calls.findIndex((c) => c.startsWith("students:"));
    const lastLearnerFetch = calls.map((c) => c.startsWith("students:")).lastIndexOf(true);
    const firstSession = calls.findIndex((c) => c.startsWith("sessions:"));

    expect(lastClassPage).toBeLessThan(firstLearnerFetch);
    expect(lastLearnerFetch).toBeLessThan(firstSession);
  });

  it("puts the all-classes watch list first -- it is what Home's biggest card opens", () => {
    startBackgroundLoad(queryClient, ["c1", "c2"]);
    expect(calls[0]).toBe("watch");
  });

  it("fetches each class's own watch list with that class's page, not later", async () => {
    startBackgroundLoad(queryClient, ["c1", "c2"]);
    await settle();
    expect(calls.indexOf("classWatch:c1")).toBeLessThan(calls.indexOf("students:c1"));
    expect(calls.indexOf("classWatch:c2")).toBeLessThan(calls.indexOf("students:c1"));
  });

  it("keeps the class order Home showed", async () => {
    startBackgroundLoad(queryClient, ["c1", "c2", "c3"]);
    await settle();
    const pages = calls.filter((c) => c.startsWith("cohort:"));
    expect(pages).toEqual(["cohort:c1", "cohort:c2", "cohort:c3"]);
  });

  it("fetches every learner's session history", async () => {
    startBackgroundLoad(queryClient, ["c1"]);
    await settle();
    expect(calls.filter((c) => c.startsWith("sessions:"))).toEqual([
      "sessions:c1-s1",
      "sessions:c1-s2",
    ]);
  });

  it("sends one request at a time -- background work never crowds the open page", async () => {
    let inFlight = 0;
    let peak = 0;
    const track = async <T,>(value: T): Promise<T> => {
      inFlight += 1;
      peak = Math.max(peak, inFlight);
      await new Promise((r) => setTimeout(r, 1));
      inFlight -= 1;
      return value;
    };
    vi.mocked(client.getCohort).mockImplementation((id: string) => track({ classId: id } as never));
    vi.mocked(client.getClassWatchList).mockImplementation(() => track([] as never));
    vi.mocked(client.getWatchList).mockImplementation(() => track([] as never));
    vi.mocked(client.getClassStudentOverviews).mockImplementation(() => track([] as never));

    startBackgroundLoad(queryClient, ["c1", "c2", "c3"]);
    await settle();
    expect(peak).toBe(1);
  });

  it("does nothing for a teacher with no classes", () => {
    startBackgroundLoad(queryClient, []);
    expect(calls).toEqual([]);
  });
});

describe("opening a class outranks the plan", () => {
  it("moves that class's page ahead of the classes queued before it", async () => {
    startBackgroundLoad(queryClient, ["c1", "c2", "c3"]);
    // The teacher opens the LAST class a moment after signing in.
    prioritiseClass("c3");
    await settle();

    expect(calls.indexOf("cohort:c3")).toBeLessThan(calls.indexOf("cohort:c1"));
  });

  it("brings that class's learners forward too, not just its page", async () => {
    startBackgroundLoad(queryClient, ["c1", "c2", "c3"]);
    prioritiseClass("c3");
    await settle();

    // c3's learners arrive before the other classes' PAGES are done, because
    // the whole of c3's work moved, in its own tier order.
    expect(calls.indexOf("cohort:c3")).toBeLessThan(calls.indexOf("students:c3"));
    expect(calls.indexOf("students:c3")).toBeLessThan(calls.indexOf("students:c1"));
  });

  it("resumes the original order once the opened class is done", async () => {
    startBackgroundLoad(queryClient, ["c1", "c2", "c3"]);
    prioritiseClass("c3");
    await settle();

    const pages = calls.filter((c) => c.startsWith("cohort:"));
    expect(pages).toEqual(["cohort:c3", "cohort:c1", "cohort:c2"]);
  });

  it("drops nothing and repeats nothing when a class is promoted", async () => {
    startBackgroundLoad(queryClient, ["c1", "c2", "c3"]);
    prioritiseClass("c2");
    await settle();

    expect(calls.filter((c) => c.startsWith("cohort:")).sort()).toEqual([
      "cohort:c1",
      "cohort:c2",
      "cohort:c3",
    ]);
    expect(new Set(calls).size).toBe(calls.length);
  });

  it("is a no-op for a class that is already warm", async () => {
    startBackgroundLoad(queryClient, ["c1"]);
    await settle();
    const before = [...calls];
    prioritiseClass("c1");
    await settle();
    expect(calls).toEqual(before);
  });
});

describe("opening a class HOLDS the warm-up until that class is loaded", () => {
  it("loads the opened class's page, watch list and learners before resuming the plan", async () => {
    startBackgroundLoad(queryClient, ["c1", "c2", "c3"]);
    await focusClass(queryClient, "c3");

    // Everything c3 needs is in hand the moment focusClass resolves...
    expect(calls).toContain("cohort:c3");
    expect(calls).toContain("classWatch:c3");
    expect(calls).toContain("students:c3");
    // ...and no OTHER class's learners were fetched while the teacher waited.
    expect(calls.filter((c) => c.startsWith("students:"))).toEqual(["students:c3"]);
  });

  it("releases the queue afterwards, and the rest of the plan still runs", async () => {
    startBackgroundLoad(queryClient, ["c1", "c2", "c3"]);
    await focusClass(queryClient, "c3");
    expect(isBackgroundPaused()).toBe(false);

    await settle();
    expect(calls).toContain("cohort:c1");
    expect(calls).toContain("cohort:c2");
    expect(calls).toContain("students:c1");
  });

  it("opening a SECOND class holds the queue again and loads that one", async () => {
    startBackgroundLoad(queryClient, ["c1", "c2", "c3"]);
    await focusClass(queryClient, "c3");
    const afterFirst = calls.length;

    await focusClass(queryClient, "c2");
    const duringSecond = calls.slice(afterFirst);

    expect(duringSecond).toContain("students:c2");
    // The hold applies again: no third class's learners crept in.
    expect(duringSecond.filter((c) => c.startsWith("students:"))).toEqual(["students:c2"]);
  });

  it("costs nothing for a class the warm-up already finished", async () => {
    startBackgroundLoad(queryClient, ["c1"]);
    await settle();
    const before = [...calls];

    await focusClass(queryClient, "c1");

    expect(calls).toEqual(before);
    expect(isBackgroundPaused()).toBe(false);
  });

  it("releases the queue even when the class fails to load", async () => {
    vi.mocked(client.getCohort).mockRejectedValue(new Error("HTTP 503"));
    startBackgroundLoad(queryClient, ["c1", "c2"]);

    await focusClass(queryClient, "c2");

    expect(isBackgroundPaused()).toBe(false);
  });
});

describe("pausing", () => {
  it("starts no new background task while held", async () => {
    startBackgroundLoad(queryClient, ["c1", "c2", "c3"]);
    pauseBackgroundLoad();
    await settle();
    const whilePaused = [...calls];

    await new Promise((resolve) => setTimeout(resolve, 5));
    expect(calls).toEqual(whilePaused);
  });

  it("picks the plan back up, in order, when released", async () => {
    startBackgroundLoad(queryClient, ["c1", "c2", "c3"]);
    pauseBackgroundLoad();
    await settle();

    resumeBackgroundLoad();
    await settle();

    expect(calls.filter((c) => c.startsWith("cohort:"))).toEqual([
      "cohort:c1",
      "cohort:c2",
      "cohort:c3",
    ]);
  });

  it("a cancelled plan never leaves the next one held", async () => {
    startBackgroundLoad(queryClient, ["c1"]);
    pauseBackgroundLoad();
    cancelBackgroundLoad();
    expect(isBackgroundPaused()).toBe(false);

    startBackgroundLoad(queryClient, ["c9"]);
    await settle();
    expect(calls).toContain("cohort:c9");
  });
});

describe("pausing stops the request already in flight, not just the next one", () => {
  /** A fetch that only settles when told to, and that honours its signal. */
  function controllable() {
    let release!: () => void;
    const started = new Promise<void>((resolve) => {
      release = resolve;
    });
    return { started, release };
  }

  it("aborts the in-flight request so it stops competing with the opened page", async () => {
    let seenSignal: AbortSignal | undefined;
    const gate = controllable();
    vi.mocked(client.getWatchList).mockImplementation(async (opts) => {
      calls.push("watch");
      seenSignal = opts?.signal;
      await gate.started;
      return [] as never;
    });

    startBackgroundLoad(queryClient, ["c1", "c2"]);
    await new Promise((r) => setTimeout(r, 0));
    expect(seenSignal?.aborted).toBe(false);

    pauseBackgroundLoad();

    expect(seenSignal?.aborted).toBe(true);
    gate.release();
  });

  it("puts the aborted task back, so pausing loses no work", async () => {
    const gate = controllable();
    let calledTimes = 0;
    vi.mocked(client.getWatchList).mockImplementation(async (opts) => {
      calls.push("watch");
      calledTimes += 1;
      if (calledTimes === 1) {
        await gate.started;
        // Behave like fetch: reject once aborted.
        if (opts?.signal?.aborted) throw new Error("AbortError");
      }
      return [] as never;
    });

    startBackgroundLoad(queryClient, ["c1"]);
    await new Promise((r) => setTimeout(r, 0));
    pauseBackgroundLoad();
    gate.release();
    await new Promise((r) => setTimeout(r, 0));

    resumeBackgroundLoad();
    await settle();

    // Re-run from the start, and the rest of the plan still happened.
    expect(calledTimes).toBe(2);
    expect(calls).toContain("cohort:c1");
  });

  it("passes a signal to every background read", async () => {
    const signals: (AbortSignal | undefined)[] = [];
    const record = (opts?: { signal?: AbortSignal }) => signals.push(opts?.signal);
    vi.mocked(client.getWatchList).mockImplementation(async (o) => (record(o), [] as never));
    vi.mocked(client.getCohort).mockImplementation(async (id, o) => (record(o), { classId: id } as never));
    vi.mocked(client.getClassWatchList).mockImplementation(async (_id, o) => (record(o), [] as never));
    vi.mocked(client.getClassStudentOverviews).mockImplementation(async (id, o) => {
      record(o);
      return [
        { studentId: `${id}-s1`, overview: {} as never, recommendations: [] as never },
      ] as never;
    });
    vi.mocked(client.getStudentSessions).mockImplementation(async (_id, o) => (record(o), [] as never));

    startBackgroundLoad(queryClient, ["c1"]);
    await settle();

    expect(signals.length).toBeGreaterThan(0);
    expect(signals.every((s) => s instanceof AbortSignal)).toBe(true);
  });

  it("a screen's own read is never given one -- a screen wants its data", async () => {
    // focusClass loads the class the teacher is looking at; nothing may cancel it.
    const seen: (AbortSignal | undefined)[] = [];
    vi.mocked(client.getCohort).mockImplementation(async (id, o) => {
      seen.push(o?.signal);
      return { classId: id } as never;
    });
    await focusClass(queryClient, "c1");
    expect(seen).toEqual([undefined]);
  });
});

describe("holds do not stomp each other", () => {
  // REGRESSION. `paused` was one boolean with three owners, so whichever let
  // go first released the others' hold too: opening a class made focusClass
  // resume the queue while the SCREEN that opened it was still loading, and
  // Home planning a warm-up cleared the navigation hold outright.
  it("focusClass releases only its own hold, not the open screen's", async () => {
    startBackgroundLoad(queryClient, ["c1", "c2"]);
    pauseBackgroundLoad(NAVIGATION_HOLD);

    await focusClass(queryClient, "c2");

    // focusClass is done, but the screen has not said it is idle yet.
    expect(isBackgroundPaused()).toBe(true);
    const afterFocus = [...calls];
    await settle();
    expect(calls).toEqual(afterFocus);

    resumeBackgroundLoad(NAVIGATION_HOLD);
    await settle();
    expect(calls).toContain("cohort:c1");
  });

  it("planning a new warm-up never releases the open screen's hold", async () => {
    pauseBackgroundLoad(NAVIGATION_HOLD);
    startBackgroundLoad(queryClient, ["c1", "c2"]);
    await settle();

    expect(isBackgroundPaused()).toBe(true);
    expect(calls).toEqual([]);

    resumeBackgroundLoad(NAVIGATION_HOLD);
    await settle();
    expect(calls).toContain("cohort:c1");
  });

  it("releasing a hold nobody took changes nothing", async () => {
    startBackgroundLoad(queryClient, ["c1"]);
    pauseBackgroundLoad(NAVIGATION_HOLD);
    resumeBackgroundLoad("someone-else");
    expect(isBackgroundPaused()).toBe(true);
  });
});

describe("cancelling", () => {
  it("stops the warm-up, so one teacher's data never lands in the next one's cache", async () => {
    startBackgroundLoad(queryClient, ["c1", "c2", "c3"]);
    cancelBackgroundLoad();
    await settle();
    // Whatever was already in flight may finish; nothing new may start.
    expect(calls.filter((c) => c.startsWith("students:"))).toEqual([]);
  });

  it("a second plan replaces the first rather than running beside it", async () => {
    startBackgroundLoad(queryClient, ["c1", "c2"]);
    startBackgroundLoad(queryClient, ["c9"]);
    await settle();
    expect(calls).toContain("cohort:c9");
    expect(calls).not.toContain("cohort:c2");
  });
});
