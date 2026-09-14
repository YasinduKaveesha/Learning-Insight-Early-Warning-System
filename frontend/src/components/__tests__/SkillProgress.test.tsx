import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SkillProgressRow } from "../student/SkillProgress";

describe("SkillProgressRow", () => {
  it("a null relativeLevel renders no bar and 'Not enough data', never a flat line", () => {
    const { container } = render(
      <SkillProgressRow
        skill={{
          skillId: "counting",
          displayName: "Counting",
          direction: "unknown",
          relativeLevel: null,
          practiceCount: 999,
        }}
        bounds={{ min: -0.5, max: 0.5 }}
        colorIndex={0}
      />,
    );
    expect(screen.getByText("Not enough data")).toBeInTheDocument();
    // No bar element should exist at all — not even a zero-width one.
    expect(container.querySelector(".bg-skillBar-1")).toBeNull();
  });

  it("a real relativeLevel renders a bar, no number or percentage label", () => {
    const { container } = render(
      <SkillProgressRow
        skill={{
          skillId: "counting",
          displayName: "Counting",
          direction: "improving",
          relativeLevel: 0.1,
          practiceCount: 4,
        }}
        bounds={{ min: -0.5, max: 0.5 }}
        colorIndex={0}
      />,
    );
    const bar = container.querySelector(".bg-skillBar-1");
    expect(bar).not.toBeNull();
    expect(container.textContent).not.toMatch(/\d+%/);
    expect(container.textContent).not.toMatch(/0\.\d+/); // no raw relativeLevel number
  });

  it("never renders practiceCount", () => {
    const { container } = render(
      <SkillProgressRow
        skill={{
          skillId: "counting",
          displayName: "Counting",
          direction: "improving",
          relativeLevel: 0.1,
          practiceCount: 42,
        }}
        bounds={{ min: -0.5, max: 0.5 }}
        colorIndex={0}
      />,
    );
    expect(container.textContent).not.toContain("42");
  });

  it("never renders a 'Mastered' badge or any threshold language", () => {
    const { container } = render(
      <SkillProgressRow
        skill={{
          skillId: "counting",
          displayName: "Counting",
          direction: "improving",
          relativeLevel: 0.49,
          practiceCount: 4,
        }}
        bounds={{ min: -0.5, max: 0.5 }}
        colorIndex={0}
      />,
    );
    expect(container.textContent?.toLowerCase()).not.toContain("mastered");
  });
  it("D42: a mastery bar with a withheld direction draws the bar and no direction word", () => {
    const { container } = render(
      <SkillProgressRow
        skill={{
          skillId: "counting",
          displayName: "Counting",
          direction: "unknown",
          relativeLevel: 0.27,
          practiceCount: 4,
        }}
        bounds={{ min: 0, max: 1 }}
        colorIndex={0}
      />,
    );
    const bar = container.querySelector(".bg-skillBar-1") as HTMLElement | null;
    expect(bar).not.toBeNull();
    expect(bar!.style.width).toBe("27%");
    expect(container.textContent?.toLowerCase()).not.toContain("not enough data");
    expect(container.textContent).not.toMatch(/0\.27|27%/);
  });

  it("D46: a never-practised skill says so, and draws no bar", () => {
    const { container } = render(
      <SkillProgressRow
        skill={{
          skillId: "division",
          displayName: "Division",
          direction: "unknown",
          // The backend sends no level for a never-practised skill; this also proves the row
          // would not draw one even if a level arrived.
          relativeLevel: 0.15,
          practiceCount: 0,
          neverPractised: true,
        }}
        bounds={{ min: 0, max: 1 }}
        colorIndex={0}
      />,
    );
    expect(screen.getByText("Not practised yet")).toBeInTheDocument();
    expect(screen.queryByText("Not enough data")).toBeNull();
    expect(container.querySelector(".bg-skillBar-1")).toBeNull();
  });

  it("D46: 'Not practised yet' and 'Not enough data' are never the same message", () => {
    const base = {
      skillId: "division",
      displayName: "Division",
      direction: "unknown" as const,
      relativeLevel: null,
      practiceCount: 2,
    };
    const practised = render(
      <SkillProgressRow skill={base} bounds={{ min: 0, max: 1 }} colorIndex={0} />,
    );
    expect(practised.container.textContent).toContain("Not enough data");
    practised.unmount();

    const untested = render(
      <SkillProgressRow
        skill={{ ...base, neverPractised: true }}
        bounds={{ min: 0, max: 1 }}
        colorIndex={0}
      />,
    );
    expect(untested.container.textContent).toContain("Not practised yet");
  });

  it("a known direction with no bar position shows the direction, not 'Not enough data'", () => {
    // The real backend's shape today: direction computed, relative_level null.
    const { container } = render(
      <SkillProgressRow
        skill={{
          skillId: "number_sense",
          displayName: "Number sense",
          direction: "improving",
          relativeLevel: null,
          practiceCount: 11,
        }}
        bounds={{ min: -0.5, max: 0.5 }}
        colorIndex={0}
      />,
    );
    expect(screen.getByText("improving")).toBeInTheDocument();
    expect(screen.queryByText("Not enough data")).toBeNull();
    expect(container.querySelector(".bg-skillBar-1")).toBeNull();
  });

});
