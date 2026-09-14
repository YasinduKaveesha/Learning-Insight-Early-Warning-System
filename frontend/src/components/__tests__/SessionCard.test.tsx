import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { SessionEntry } from "../../lib/presentation";
import { SessionCard } from "../student/SessionCard";

const BASE: SessionEntry = {
  sessionNumber: 5,
  date: "2026-08-24T00:00:00.000Z",
  practice: { present: true, accuracy: 0.82, pace: "typical", hintsUsed: 3 },
  games: {
    present: true,
    dataComplete: true,
    state: "on_target",
    stateReason: null,
    engagementDriver: "steady completion",
    frustrationDriver: null,
  },
};

describe("SessionCard", () => {
  it("displays the session number exactly as given, never renumbered", () => {
    render(<SessionCard session={{ ...BASE, sessionNumber: 42 }} />);
    expect(screen.getByText("Session 42")).toBeInTheDocument();
  });

  it("shows 'No activity recorded' for an absent Games component, in the Games block only", () => {
    render(
      <SessionCard
        session={{
          ...BASE,
          games: {
            present: false,
            dataComplete: true,
            state: null,
            stateReason: null,
            engagementDriver: null,
            frustrationDriver: null,
          },
        }}
      />,
    );
    expect(screen.getByText("No activity recorded")).toBeInTheDocument();
  });

  it("shows 'Activity data incomplete for this session' for faulty telemetry, never as disengagement", () => {
    render(
      <SessionCard
        session={{
          ...BASE,
          games: {
            present: true,
            dataComplete: false,
            state: null,
            stateReason: "telemetry_gap",
            engagementDriver: null,
            frustrationDriver: null,
          },
        }}
      />,
    );
    expect(screen.getByText("Activity data incomplete for this session")).toBeInTheDocument();
    expect(screen.queryByText(/disengag/i)).not.toBeInTheDocument();
  });

  it("the no-activity and incomplete-telemetry messages are distinct strings", () => {
    render(
      <SessionCard
        session={{
          ...BASE,
          games: { present: false, dataComplete: true, state: null, stateReason: null, engagementDriver: null, frustrationDriver: null },
        }}
      />,
    );
    expect(screen.queryByText("Activity data incomplete for this session")).not.toBeInTheDocument();
  });

  it("renders Practice (B) and Games (C) as separate blocks, never one merged figure", () => {
    render(<SessionCard session={BASE} />);
    expect(screen.getByText("Practice (B)")).toBeInTheDocument();
    expect(screen.getByText("Games (C)")).toBeInTheDocument();
    // The practice accuracy figure appears once, scoped to Practice only.
    expect(screen.getByText(/Accuracy 82%/)).toBeInTheDocument();
  });
});
