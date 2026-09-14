import { describe, expect, it } from "vitest";
import { lastActiveLabel } from "../format";

describe("lastActiveLabel", () => {
  it("never renders a dangling 'Last active' with nothing after it", () => {
    // A child who joined a class today has no last-active date at all. The card
    // used to print the label followed by a blank, which reads as a value that
    // failed to load rather than a child who has not started. Seen on the first
    // real join, 2026-09-14.
    expect(lastActiveLabel("")).toBe("No activity yet");
    expect(lastActiveLabel(null)).toBe("No activity yet");
    expect(lastActiveLabel(undefined)).toBe("No activity yet");
    expect(lastActiveLabel("   ")).toBe("No activity yet");
  });

  it("includes the label and the relative date when there is activity", () => {
    const now = new Date("2026-09-14T12:00:00Z");
    expect(lastActiveLabel("2026-09-14T09:00:00Z", now)).toBe("Last active Today");
    expect(lastActiveLabel("2026-09-13T09:00:00Z", now)).toBe("Last active Yesterday");
  });
});
