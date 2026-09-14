import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { WatchStatus } from "../../lib/presentation";
import { assertNever } from "../../lib/presentation";
import { WatchStatusBadge } from "../status/WatchStatusBadge";

describe("WatchStatusBadge", () => {
  it("renders the watching state with icon and text", () => {
    render(
      <WatchStatusBadge
        status={{ kind: "watching", label: "Worth watching right now", priority: 1 }}
      />,
    );
    expect(screen.getByText("Worth watching right now")).toBeInTheDocument();
    expect(screen.getByText("◐")).toBeInTheDocument();
  });

  it("renders the no_concern state with icon and text", () => {
    render(<WatchStatusBadge status={{ kind: "no_concern", label: "No current concern identified" }} />);
    expect(screen.getByText("No current concern identified")).toBeInTheDocument();
    expect(screen.getByText("○")).toBeInTheDocument();
  });

  it("renders the getting_started state with icon and text", () => {
    render(
      <WatchStatusBadge
        status={{
          kind: "getting_started",
          label: "Getting Started",
          sessionsCompleted: 1,
          sessionsRequired: 3,
        }}
      />,
    );
    expect(screen.getByText("Getting Started")).toBeInTheDocument();
    expect(screen.getByText("◔")).toBeInTheDocument();
  });

  it("never falls through to a reassuring default for an unrecognised status", () => {
    // The component's own switch uses assertNever, so an invalid `kind`
    // cannot be constructed by TypeScript. This proves the escape hatch
    // itself throws rather than silently returning a default — the runtime
    // half of the guarantee the discriminated union provides at compile time.
    const bogus = { kind: "unknown_status" } as unknown as never;
    expect(() => assertNever(bogus)).toThrow();
  });

  it("watch status is conveyed by text, not colour alone, in every state", () => {
    const statuses: WatchStatus[] = [
      { kind: "watching", label: "Worth watching right now", priority: 1 },
      { kind: "no_concern", label: "No current concern identified" },
      { kind: "getting_started", label: "Getting Started", sessionsCompleted: 1, sessionsRequired: 3 },
    ];
    for (const status of statuses) {
      const { unmount } = render(<WatchStatusBadge status={status} />);
      expect(screen.getByText(status.label)).toBeInTheDocument();
      unmount();
    }
  });
});
