import { describe, expect, it } from "vitest";
import type { LearnerSnapshot, SkillProgress } from "../types";
import {
  ALL_CLASS_STUDENTS,
  GETTING_STARTED_SNAPSHOT,
  GETTING_STARTED_STUDENT_ID,
  ROSTER_SNAPSHOTS,
  sessionsForGettingStarted,
  sessionsForStudent,
  skillProgressFor,
} from "../mock/fixtures/authored";
import { MockClient } from "../mock/mockClient";
import { toWatchStatus } from "../../lib/presentation";
import realSnapshotsAtT7 from "../mock/fixtures/realSnapshotsAtT7.json";

function allSnapshots(): LearnerSnapshot[] {
  return Object.values(ALL_CLASS_STUDENTS).flat();
}

// Fields that must never appear anywhere in a fixture (plan §5, §7, rule 3-F1).
const FORBIDDEN_FIELDS = [
  "population",
  "dd_subtype",
  "prob_class_0",
  "prob_class_1",
  "prob_class_2",
  "predicted_class",
  "actual_class",
  "risk_level",
  "risk_score",
];

// Raw feature/column names that must never leak into a display string.
const RAW_FEATURE_NAMES = [
  "score_trend_slope",
  "engagement_decline_rate",
  "ipsatised_mastery",
  "sessions_observed",
  "is_first_snapshot",
  "hint_intensity_x_accuracy",
];

describe("fixtures: no forbidden fields", () => {
  it("no snapshot object contains an audit label or a probability field", () => {
    for (const snapshot of allSnapshots()) {
      const json = JSON.stringify(snapshot);
      for (const field of FORBIDDEN_FIELDS) {
        expect(json.toLowerCase()).not.toContain(field.toLowerCase());
      }
    }
  });

  it("no explanation contains a raw feature name", () => {
    for (const snapshot of allSnapshots()) {
      if (!snapshot.explanation) continue;
      for (const name of RAW_FEATURE_NAMES) {
        expect(snapshot.explanation).not.toContain(name);
      }
    }
  });
});

describe("fixtures: 280-char explanation contract", () => {
  it("every explanation is within 280 characters", () => {
    for (const snapshot of allSnapshots()) {
      if (snapshot.explanation !== null) {
        expect(snapshot.explanation.length).toBeLessThanOrEqual(280);
      }
    }
  });
});

describe("fixtures: type conformance", () => {
  it("every roster snapshot has the shape of LearnerSnapshot", () => {
    for (const s of ROSTER_SNAPSHOTS) {
      expect(typeof s.studentId).toBe("string");
      expect(typeof s.displayName).toBe("string");
      expect(typeof s.classId).toBe("string");
      expect(typeof s.sessionNumber).toBe("number");
      expect(typeof s.watchFlag).toBe("boolean");
      expect(["number", "object"]).toContain(typeof s.rankWithinSnapshot); // number or null
      expect(typeof s.evidenceStatus).toBe("string");
      expect(typeof s.sessionsCompleted).toBe("number");
      expect(s.practiceTrajectory.source).toBe("practice_accuracy");
      expect(Array.isArray(s.accuracySparkline)).toBe(true);
      expect(Array.isArray(s.engagementSparkline)).toBe(true);
      expect(typeof s.modelVersion).toBe("string");
      expect(typeof s.inferenceTimestamp).toBe("string");
    }
  });

  it("every skill progress row has the shape of SkillProgress", () => {
    const skills: SkillProgress[] = skillProgressFor(ROSTER_SNAPSHOTS[0]!.studentId);
    expect(skills).toHaveLength(7);
    for (const skill of skills) {
      expect(typeof skill.skillId).toBe("string");
      expect(typeof skill.displayName).toBe("string");
      expect(["improving", "not_moving", "unknown"]).toContain(skill.direction);
      expect(["number", "object"]).toContain(typeof skill.relativeLevel);
      expect(typeof skill.practiceCount).toBe("number");
    }
  });
});

describe("fixtures: Getting Started", () => {
  it("maps to kind getting_started via toWatchStatus", () => {
    const status = toWatchStatus(GETTING_STARTED_SNAPSHOT);
    expect(status.kind).toBe("getting_started");
  });

  it("does not appear in any watch-list fixture response", async () => {
    const client = new MockClient();
    const teacherWide = await client.getWatchList();
    const perClass = await client.getClassWatchList("class-3blue");
    expect(teacherWide.students.some((s) => s.studentId === GETTING_STARTED_STUDENT_ID)).toBe(
      false,
    );
    expect(perClass.students.some((s) => s.studentId === GETTING_STARTED_STUDENT_ID)).toBe(
      false,
    );
  });

  it("has sessions_completed of 1 (not the sessionsRequired floor of 3)", () => {
    expect(GETTING_STARTED_SNAPSHOT.sessionsCompleted).toBe(1);
  });
});

describe("fixtures: session-history gap states", () => {
  const sessions = sessionsForStudent("STU-0004", 7);
  const gettingStartedSessions = sessionsForGettingStarted();

  it("has at least one session with no Component C activity", () => {
    expect(sessions.some((s) => !s.games.present)).toBe(true);
  });

  it("has at least one session with incomplete telemetry", () => {
    expect(sessions.some((s) => s.games.present && !s.games.dataComplete)).toBe(true);
  });

  it("the no-activity and incomplete-telemetry sessions are distinct sessions", () => {
    const noActivity = sessions.find((s) => !s.games.present);
    const incomplete = sessions.find((s) => s.games.present && !s.games.dataComplete);
    expect(noActivity).toBeDefined();
    expect(incomplete).toBeDefined();
    expect(noActivity!.sessionNumber).not.toBe(incomplete!.sessionNumber);
  });

  it("Getting Started's single session has both components present and complete", () => {
    expect(gettingStartedSessions).toHaveLength(1);
    expect(gettingStartedSessions[0]!.games.present).toBe(true);
    expect(gettingStartedSessions[0]!.games.dataComplete).toBe(true);
  });
});

describe("fixtures: ranking", () => {
  // The authoritative check: the full real t=7 snapshot (90 students) is the
  // group ranks were actually computed within (scripts/build-fixtures.mjs).
  // The roster is a display subset of it, so contiguity is asserted here,
  // not against the roster alone.
  const fullSnapshot = realSnapshotsAtT7 as unknown as LearnerSnapshot[];

  it("ranks are contiguous within the full snapshot, starting at 1, no gaps", () => {
    const ranks = fullSnapshot
      .filter((s) => s.watchFlag)
      .map((s) => s.rankWithinSnapshot)
      .filter((r): r is number => r !== null)
      .sort((a, b) => a - b);
    expect(ranks[0]).toBe(1);
    ranks.forEach((r, i) => expect(r).toBe(i + 1));
  });

  it("every watched student in the full snapshot has a unique rank", () => {
    const ranks = fullSnapshot.filter((s) => s.watchFlag).map((s) => s.rankWithinSnapshot);
    expect(new Set(ranks).size).toBe(ranks.length);
  });

  it("no non-watched student in the full snapshot carries a rank", () => {
    expect(fullSnapshot.filter((s) => !s.watchFlag).every((s) => s.rankWithinSnapshot === null)).toBe(
      true,
    );
  });

  it("no rank leaks across the Getting Started student, whose rank is always null", () => {
    expect(GETTING_STARTED_SNAPSHOT.rankWithinSnapshot).toBeNull();
  });
});

describe("mockClient: returns typed data for every endpoint", () => {
  const client = new MockClient();

  it("getHome", async () => {
    const home = await client.getHome();
    expect(home.disclosure.length).toBeGreaterThan(0);
    expect(home.classes.length).toBeGreaterThan(0);
  });

  it("getCohort", async () => {
    const cohort = await client.getCohort("class-3blue");
    expect(cohort.students.length).toBeGreaterThan(0);
  });

  it("getClassWatchList", async () => {
    const list = await client.getClassWatchList("class-3blue");
    expect(Array.isArray(list.students)).toBe(true);
  });

  it("getWatchList", async () => {
    const list = await client.getWatchList();
    expect(Array.isArray(list.students)).toBe(true);
  });

  it("getStudentOverview", async () => {
    const overview = await client.getStudentOverview(ROSTER_SNAPSHOTS[0]!.studentId);
    expect(overview.snapshot.studentId).toBe(ROSTER_SNAPSHOTS[0]!.studentId);
    expect(overview.skills.length).toBe(7);
  });

  it("getStudentSessions", async () => {
    const sessions = await client.getStudentSessions(ROSTER_SNAPSHOTS[0]!.studentId);
    expect(sessions.length).toBeGreaterThan(0);
  });
});
