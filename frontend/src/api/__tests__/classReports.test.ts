import { describe, expect, it } from "vitest";
import { MockClient } from "../mock/mockClient";

// Uses the REAL MockClient — this is what actually catches a research
// metric leaking in from the fixtures, since the test-file version in
// routes/__tests__/ClassroomReportsRoute.test.tsx only exercises a
// hand-written stub response.
describe("MockClient — getClassReports (Step 7)", () => {
  const FORBIDDEN_TERMS = [
    "precision",
    "recall",
    "f1",
    "f-1",
    "auc",
    "lift",
    "calibration",
    "confusion matrix",
    "brier",
    "prob_class",
    "predicted_class",
    "population",
    "dd_subtype",
  ];

  it("the real response for a seed class carries no research-metric or audit-only field", async () => {
    const client = new MockClient();
    const reports = await client.getClassReports("class-3blue");
    const serialised = JSON.stringify(reports).toLowerCase();
    for (const term of FORBIDDEN_TERMS) expect(serialised).not.toContain(term);
  });

  it("returns real, non-empty data for a class with a roster, and no dead studentsToWatchOverTime field", async () => {
    const client = new MockClient();
    const reports = await client.getClassReports("class-3blue");
    expect(reports.classLearningProgress.values.length).toBeGreaterThan(0);
    expect(reports.earlyWarningTrend.flagRates.length).toBeGreaterThan(0);
    expect(reports.participation.length).toBe(3);
    expect(reports.earlyWarningTrend.explanation.length).toBeGreaterThan(0);
    // Step 8 fix: removed entirely, not just unused — no dead data left
    // behind for a screen to accidentally render as a second chart.
    expect(reports).not.toHaveProperty("studentsToWatchOverTime");
  });

  it("participation counts sum to no more than the class roster size", async () => {
    const client = new MockClient();
    const cohort = await client.getCohort("class-3blue");
    const reports = await client.getClassReports("class-3blue");
    const total = reports.participation.reduce((sum, b) => sum + b.studentCount, 0);
    expect(total).toBeLessThanOrEqual(cohort.studentCount);
  });

  it("does not throw for a class with an empty roster", async () => {
    const client = new MockClient();
    const created = await client.createClass("Reports Empty Roster Test", "GRADE_2");
    await expect(client.getClassReports(created.classId)).resolves.toBeDefined();
  });
});
