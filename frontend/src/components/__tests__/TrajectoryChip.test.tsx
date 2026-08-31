import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { TrajectoryState } from "../../lib/presentation";
import { TrajectoryChip } from "../status/TrajectoryChip";

describe("TrajectoryChip", () => {
  const states: TrajectoryState[] = ["improving", "stable", "needs_attention", "unknown"];

  it.each(states)("state %s always renders with the 'Practice accuracy' source prefix", (state) => {
    render(<TrajectoryChip trajectory={{ source: "practice_accuracy", state }} />);
    const text = screen.getByText(/Practice accuracy:/);
    expect(text).toBeInTheDocument();
  });

  it("a null-slope (unknown) state reads 'not enough data', never a flat line", () => {
    render(<TrajectoryChip trajectory={{ source: "practice_accuracy", state: "unknown" }} />);
    expect(screen.getByText("Practice accuracy: not enough data")).toBeInTheDocument();
    expect(screen.queryByText(/flat/i)).not.toBeInTheDocument();
  });
});
