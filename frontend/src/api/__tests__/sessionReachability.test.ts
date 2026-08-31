import { describe, expect, it } from "vitest";
import { MockClient } from "../mock/mockClient";

// Confirms the Step 3 report's claim can actually be walked from the real
// seam, not just asserted from a hand-written fixture object: Nimal
// (STU-0004) is a real roster member of a real class, and his session list
// — reached exactly the way StudentSessionsRoute reaches it — contains both
// hand-authored gap states.
describe("MockClient — the two hand-authored session gap fixtures are reachable", () => {
  it("Nimal (STU-0004) is a roster member of a real, navigable class", async () => {
    const client = new MockClient();
    const cohort = await client.getCohort("class-3blue");
    const nimal = cohort.students.find((s) => s.studentId === "STU-0004");
    expect(nimal).toBeDefined();
    expect(nimal!.displayName).toBe("Nimal");
  });

  it("Nimal's real session list (as StudentSessionsRoute would fetch it) contains a no-Component-C session", async () => {
    const client = new MockClient();
    const sessions = await client.getStudentSessions("STU-0004");
    expect(sessions.some((s) => !s.games.present)).toBe(true);
  });

  it("Nimal's real session list contains an incomplete-telemetry session", async () => {
    const client = new MockClient();
    const sessions = await client.getStudentSessions("STU-0004");
    expect(sessions.some((s) => s.games.present && !s.games.dataComplete)).toBe(true);
  });
});
