import { describe, expect, it } from "vitest";
import type { EvidenceStatus, LearnerSnapshot } from "../../api/types";
import {
  filterExplanation,
  recommendationLabel,
  skillBarPositionFromBounds,
  skillDirectionLabel,
  sortCohortOrder,
  toWatchStatus,
  trajectoryLabel,
} from "../presentation";

function makeSnapshot(overrides: Partial<LearnerSnapshot> = {}): LearnerSnapshot {
  return {
    studentId: "00000000-0000-0000-0000-000000000000",
    displayName: "Test Student",
    classId: "class-1",
    sessionNumber: 5,
    watchFlag: false,
    rankWithinSnapshot: null,
    evidenceStatus: "sufficient_evidence",
    sessionsCompleted: 5,
    practiceTrajectory: { source: "practice_accuracy", state: "stable" },
    // D17: no engagementTrajectory field on LearnerSnapshot.
    explanation: null,
    lastActiveDate: "2026-08-29T00:00:00.000Z",
    accuracySparkline: [],
    engagementSparkline: [],
    modelVersion: "v1",
    inferenceTimestamp: "2026-08-30T00:00:00.000Z",
    ...overrides,
  };
}

describe("toWatchStatus", () => {
  it("returns watching when flagged with sufficient evidence", () => {
    const status = toWatchStatus(
      makeSnapshot({ watchFlag: true, rankWithinSnapshot: 3 }),
    );
    expect(status.kind).toBe("watching");
    expect(status).toEqual({
      kind: "watching",
      label: "Worth watching right now",
      priority: 3,
    });
  });

  it("returns no_concern when not flagged with sufficient evidence", () => {
    const status = toWatchStatus(makeSnapshot({ watchFlag: false }));
    expect(status).toEqual({
      kind: "no_concern",
      label: "No current concern identified",
    });
  });

  it("returns getting_started for insufficient_exposure", () => {
    const status = toWatchStatus(
      makeSnapshot({ evidenceStatus: "insufficient_exposure", sessionsCompleted: 1 }),
    );
    expect(status.kind).toBe("getting_started");
  });

  const nonSufficientStatuses: EvidenceStatus[] = [
    "insufficient_exposure",
    "insufficient_future_evidence",
    "censored_by_observation_end",
    "administratively_missing",
  ];

  it.each(nonSufficientStatuses)(
    "maps every non-sufficient evidence status (%s) to getting_started",
    (evidenceStatus) => {
      const status = toWatchStatus(makeSnapshot({ evidenceStatus }));
      expect(status.kind).toBe("getting_started");
    },
  );

  it("returns getting_started when watchFlag is true but evidence is insufficient — never watching", () => {
    const status = toWatchStatus(
      makeSnapshot({
        watchFlag: true,
        rankWithinSnapshot: 1,
        evidenceStatus: "insufficient_exposure",
        sessionsCompleted: 1,
      }),
    );
    expect(status.kind).toBe("getting_started");
    expect(status.kind).not.toBe("watching");
  });

  it("never produces a status outside the three defined kinds", () => {
    const kinds = [
      toWatchStatus(makeSnapshot({ watchFlag: true, rankWithinSnapshot: 1 })).kind,
      toWatchStatus(makeSnapshot({ watchFlag: false })).kind,
      toWatchStatus(makeSnapshot({ evidenceStatus: "administratively_missing" })).kind,
    ];
    for (const kind of kinds) {
      expect(["watching", "no_concern", "getting_started"]).toContain(kind);
    }
  });
});

describe("trajectoryLabel", () => {
  it("always includes the source prefix", () => {
    expect(trajectoryLabel({ source: "practice_accuracy", state: "needs_attention" })).toBe(
      "Practice accuracy: ↓ needs attention",
    );
    expect(trajectoryLabel({ source: "game_engagement", state: "stable" })).toBe(
      "Game engagement: → stable",
    );
  });

  it("a null/unknown slope reads as not enough data, never a flat line", () => {
    const label = trajectoryLabel({ source: "practice_accuracy", state: "unknown" });
    expect(label).toContain("not enough data");
    expect(label.toLowerCase()).not.toContain("flat");
  });

  it("cannot be produced without a source, by construction of the Trajectory type", () => {
    // trajectoryLabel's only parameter is a Trajectory, which always carries `source`.
    // There is no overload or code path that accepts a bare TrajectoryState.
    expect(trajectoryLabel).toHaveLength(1);
  });
});

describe("skillDirectionLabel", () => {
  it("never returns 'flat' for an unknown direction", () => {
    const label = skillDirectionLabel("unknown");
    expect(label).toBe("not enough data");
    expect(label.toLowerCase()).not.toContain("flat");
  });

  it("maps improving and not_moving correctly", () => {
    expect(skillDirectionLabel("improving")).toBe("improving");
    expect(skillDirectionLabel("not_moving")).toBe("not moving");
  });
});

describe("skillBarPositionFromBounds", () => {
  const bounds = { min: -0.5, max: 0.5 };

  it("returns null for a null relative level — never a rendered 0/empty bar", () => {
    expect(skillBarPositionFromBounds(null, bounds)).toBeNull();
  });

  it("returns a plain number, never a string with a % sign, for a real level", () => {
    const result = skillBarPositionFromBounds(0, bounds);
    expect(typeof result).toBe("number");
  });

  it("clamps within the given bounds", () => {
    expect(skillBarPositionFromBounds(-1, bounds)).toBe(0);
    expect(skillBarPositionFromBounds(1, bounds)).toBe(100);
  });
});

describe("recommendationLabel", () => {
  it("maps all four known kinds", () => {
    expect(recommendationLabel("practice")).toBe("Practice");
    expect(recommendationLabel("review")).toBe("Review");
    expect(recommendationLabel("try_again")).toBe("Try Again");
    expect(recommendationLabel("monitor_progress")).toBe("Monitor Progress");
  });

  it("returns a readable fallback for an unknown kind instead of throwing", () => {
    expect(() => recommendationLabel("some_new_kind")).not.toThrow();
    expect(recommendationLabel("some_new_kind")).toBe("Suggestion");
  });
});

describe("filterExplanation", () => {
  it("rejects an explanation whose reason is the observation/time index", () => {
    const result = filterExplanation(
      "This reflects a longer observation history for this learner.",
      true,
    );
    expect(result).toBeNull();
  });

  it("rejects a protective/reassuring sentence on a flagged student", () => {
    const result = filterExplanation(
      "Skill mastery is progressing at a healthy pace.",
      true,
    );
    expect(result).toBeNull();
  });

  it("allows a protective sentence through for a student who is not flagged", () => {
    const result = filterExplanation(
      "Skill mastery is progressing at a healthy pace.",
      false,
    );
    expect(result).not.toBeNull();
  });

  it("passes through a legitimate explanation unchanged", () => {
    const text =
      "Subtraction has not improved across the last four sessions, and hints are rarely being used.";
    expect(filterExplanation(text, true)).toBe(text);
  });
});

describe("sortCohortOrder with no priority numbers (D39)", () => {
  it("orders flagged learners by name, deterministically, when none carries a priority", () => {
    const names = ["Zara", "Amal", "Kasun", "Dilshan", "Nimal"];
    const flagged = names.map((displayName, i) =>
      makeSnapshot({ studentId: `id-${i}`, displayName, watchFlag: true, rankWithinSnapshot: null }),
    );
    const calm = makeSnapshot({ studentId: "calm", displayName: "Aaron", watchFlag: false });
    const sorted = sortCohortOrder([calm, ...flagged]);
    expect(sorted.map((s) => s.displayName)).toEqual([
      "Amal",
      "Dilshan",
      "Kasun",
      "Nimal",
      "Zara",
      "Aaron", // no-concern still comes after every watched learner
    ]);
  });
});
