import { describe, expect, it } from "vitest";
import { isDuplicateClassNameError } from "../client";
import { MockClient } from "../mock/mockClient";

// Uses the REAL MockClient (not a vi.mock stub) — this is the one place we
// verify the actual seam implementation end to end, not just that a screen
// renders whatever it's handed.
describe("MockClient — class management (Step 6)", () => {
  it("the key shown at creation and the key retrievable later from getCohort are the SAME key", async () => {
    const client = new MockClient();
    const created = await client.createClass("Test Class Alpha", "GRADE_3");
    const cohort = await client.getCohort(created.classId);
    expect(cohort.classKey).toBe(created.classKey);
    expect(cohort.className).toBe(created.className);
    expect(cohort.grade).toBe("GRADE_3");
  });

  it("a newly created class has zero students and appears in getHome", async () => {
    const client = new MockClient();
    const created = await client.createClass("Test Class Beta", "GRADE_2");
    const cohort = await client.getCohort(created.classId);
    expect(cohort.studentCount).toBe(0);

    const home = await client.getHome();
    const card = home.classes.find((c) => c.classId === created.classId);
    expect(card).toBeDefined();
    expect(card!.studentCount).toBe(0);
  });

  it("a duplicate name (case-insensitive, trimmed) throws DuplicateClassNameError, not a crash", async () => {
    const client = new MockClient();
    await client.createClass("Test Class Gamma", "GRADE_3");
    let caught: unknown;
    try {
      await client.createClass("  test class gamma  ", "GRADE_2");
    } catch (e) {
      caught = e;
    }
    expect(isDuplicateClassNameError(caught)).toBe(true);
  });

  it("the seed class Grade 3 Blue already has a permanent key retrievable via getCohort", async () => {
    const client = new MockClient();
    const cohort = await client.getCohort("class-3blue");
    expect(cohort.classKey).toMatch(/^[0-9A-Z]{6}$/);
    // Fetching twice returns the identical key — nothing regenerates it.
    const cohortAgain = await client.getCohort("class-3blue");
    expect(cohortAgain.classKey).toBe(cohort.classKey);
  });

  it("approving a join request removes it and drops the cohort's pending count", async () => {
    const client = new MockClient();
    const before = await client.getJoinRequests("class-3blue");
    expect(before.length).toBeGreaterThan(0);
    const firstId = before[0]!.requestId;

    await client.approveJoinRequest("class-3blue", firstId);

    const after = await client.getJoinRequests("class-3blue");
    expect(after.some((r) => r.requestId === firstId)).toBe(false);
    expect(after.length).toBe(before.length - 1);

    const cohort = await client.getCohort("class-3blue");
    expect(cohort.pendingRequestCount).toBe(after.length);
  });
});
