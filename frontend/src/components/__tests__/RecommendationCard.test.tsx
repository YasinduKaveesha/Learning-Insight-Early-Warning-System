import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { RecommendationDisplay } from "../../lib/presentation";
import { RecommendationCard } from "../student/RecommendationCard";

const BASE: RecommendationDisplay = {
  recommendationId: "rec-1",
  kind: "review",
  targetSkillDisplayName: "Place value",
  evidenceSummary: "Subtraction has been practised for four sessions without improvement.",
  status: "pending",
  modifiedActionSummary: null,
  expiresAfterSession: 14,
};

describe("RecommendationCard", () => {
  it("renders the known kinds through the lookup", () => {
    for (const kind of ["practice", "review", "try_again", "monitor_progress"]) {
      const { unmount } = render(
        <RecommendationCard recommendation={{ ...BASE, kind }} onAccept={vi.fn()} onDismiss={vi.fn()} onModify={vi.fn()} />,
      );
      unmount();
    }
  });

  it("an unknown kind falls back and does not throw", () => {
    expect(() =>
      render(
        <RecommendationCard
          recommendation={{ ...BASE, kind: "some_new_kind_never_seen" }}
          onAccept={vi.fn()}
          onDismiss={vi.fn()}
          onModify={vi.fn()}
        />,
      ),
    ).not.toThrow();
    expect(screen.getByText(/Suggestion/)).toBeInTheDocument();
  });

  it("shows the evidence WITH the action, not behind a tap", () => {
    render(<RecommendationCard recommendation={BASE} onAccept={vi.fn()} onDismiss={vi.fn()} onModify={vi.fn()} />);
    expect(screen.getByText(new RegExp(BASE.evidenceSummary))).toBeInTheDocument();
  });

  it("marks a pending recommendation as 'Not yet applied' and shows expiry", () => {
    render(<RecommendationCard recommendation={BASE} onAccept={vi.fn()} onDismiss={vi.fn()} onModify={vi.fn()} />);
    expect(screen.getByText(/Not yet applied/)).toBeInTheDocument();
    expect(screen.getByText(/Expires after session 14/)).toBeInTheDocument();
  });

  it("Accept, Modify and Dismiss are labelled distinctly and are visually separated, not merely adjacent siblings", () => {
    // Step 4 review ruling A: "never adjacent" means visually, not only in
    // DOM order — a 4px spacer div satisfies the letter and not the point.
    // This asserts real visual distinction: three different visual weights
    // (solid / outline / understated-with-a-rule-above-it), not three
    // identically-styled buttons a thumb could confuse.
    render(<RecommendationCard recommendation={BASE} onAccept={vi.fn()} onDismiss={vi.fn()} onModify={vi.fn()} />);
    const accept = screen.getByRole("button", { name: "Accept" });
    const modify = screen.getByRole("button", { name: "Modify" });
    const dismiss = screen.getByRole("button", { name: "Dismiss" });

    // Distinct labels (never colour/position alone).
    expect(accept.textContent).not.toBe(modify.textContent);
    expect(modify.textContent).not.toBe(dismiss.textContent);

    // Distinct visual treatment — not three buttons sharing one className.
    expect(accept.className).not.toBe(modify.className);
    expect(modify.className).not.toBe(dismiss.className);
    expect(accept.className).not.toBe(dismiss.className);

    // Dismiss sits behind an explicit visual break (a rule + extra top
    // margin), giving it real distance from Accept — not just DOM order.
    const dismissWrapper = dismiss.parentElement!;
    expect(dismissWrapper.className).toMatch(/border-t/);
  });

  it("calls onAccept with the recommendation id", async () => {
    const onAccept = vi.fn();
    render(<RecommendationCard recommendation={BASE} onAccept={onAccept} onDismiss={vi.fn()} onModify={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Accept" }));
    expect(onAccept).toHaveBeenCalledWith("rec-1");
  });

  it("calls onDismiss with the recommendation id", async () => {
    const onDismiss = vi.fn();
    render(<RecommendationCard recommendation={BASE} onAccept={vi.fn()} onDismiss={onDismiss} onModify={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(onDismiss).toHaveBeenCalledWith("rec-1");
  });

  it("Modify opens an input and passes the captured text to onModify", async () => {
    const onModify = vi.fn();
    render(<RecommendationCard recommendation={BASE} onAccept={vi.fn()} onDismiss={vi.fn()} onModify={onModify} />);
    await userEvent.click(screen.getByRole("button", { name: "Modify" }));
    const textbox = screen.getByRole("textbox");
    await userEvent.type(textbox, "Practice place value instead of subtraction");
    await userEvent.click(screen.getByRole("button", { name: "Save change" }));
    expect(onModify).toHaveBeenCalledWith("rec-1", "Practice place value instead of subtraction");
  });

  it("does not offer to save an empty modification", async () => {
    const onModify = vi.fn();
    render(<RecommendationCard recommendation={BASE} onAccept={vi.fn()} onDismiss={vi.fn()} onModify={onModify} />);
    await userEvent.click(screen.getByRole("button", { name: "Modify" }));
    expect(screen.getByRole("button", { name: "Save change" })).toBeDisabled();
  });

  it('renders no "Accept all" control', () => {
    render(<RecommendationCard recommendation={BASE} onAccept={vi.fn()} onDismiss={vi.fn()} onModify={vi.fn()} />);
    expect(screen.queryByText(/accept all/i)).not.toBeInTheDocument();
  });
});
