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

  it("an unknown kind does not throw (UI-refinement pass: the card no longer renders a kind-derived label at all)", () => {
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
    expect(screen.getByText(BASE.targetSkillDisplayName)).toBeInTheDocument();
  });

  it("shows the evidence WITH the action, not behind a tap", () => {
    render(<RecommendationCard recommendation={BASE} onAccept={vi.fn()} onDismiss={vi.fn()} onModify={vi.fn()} />);
    expect(screen.getByText(new RegExp(BASE.evidenceSummary))).toBeInTheDocument();
  });

  // UI-refinement pass: the "Not yet applied · Expires after session N"
  // status/expiry line is removed from the card entirely, at explicit
  // direction — that also removes the only place "Accepted" / "Dismissed"
  // / "Modified: ..." feedback rendered for an already-actioned card.
  it("does not render a status/expiry line", () => {
    render(<RecommendationCard recommendation={BASE} onAccept={vi.fn()} onDismiss={vi.fn()} onModify={vi.fn()} />);
    expect(screen.queryByText(/Not yet applied/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Expires after session/)).not.toBeInTheDocument();
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

  it("Modify offers a choice of the four kinds and the seven skills — never free text", async () => {
    const onModify = vi.fn();
    render(<RecommendationCard recommendation={{ ...BASE, targetSkillId: "place_value" }} onAccept={vi.fn()} onDismiss={vi.fn()} onModify={onModify} />);
    await userEvent.click(screen.getByRole("button", { name: "Modify" }));

    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    const kind = screen.getByLabelText("What should this be changed to?");
    const skill = screen.getByLabelText("Skill");
    // The skill starts on the suggestion's own skill.
    expect(skill).toHaveValue("place_value");
    // Four kinds plus the placeholder; seven skills plus "No specific skill".
    expect(kind.querySelectorAll("option")).toHaveLength(5);
    expect(skill.querySelectorAll("option")).toHaveLength(8);

    await userEvent.selectOptions(kind, "try_again");
    await userEvent.selectOptions(skill, "subtraction");
    await userEvent.click(screen.getByRole("button", { name: "Save change" }));
    expect(onModify).toHaveBeenCalledWith("rec-1", { kind: "try_again", skillId: "subtraction" });
  });

  it("'No specific skill' sends a null skill", async () => {
    const onModify = vi.fn();
    render(<RecommendationCard recommendation={BASE} onAccept={vi.fn()} onDismiss={vi.fn()} onModify={onModify} />);
    await userEvent.click(screen.getByRole("button", { name: "Modify" }));
    await userEvent.selectOptions(screen.getByLabelText("What should this be changed to?"), "monitor_progress");
    await userEvent.click(screen.getByRole("button", { name: "Save change" }));
    expect(onModify).toHaveBeenCalledWith("rec-1", { kind: "monitor_progress", skillId: null });
  });

  it("does not offer to save a modification until a kind is chosen", async () => {
    const onModify = vi.fn();
    render(<RecommendationCard recommendation={BASE} onAccept={vi.fn()} onDismiss={vi.fn()} onModify={onModify} />);
    await userEvent.click(screen.getByRole("button", { name: "Modify" }));
    expect(screen.getByRole("button", { name: "Save change" })).toBeDisabled();
  });

  it.each([
    ["accepted", null, "You accepted this suggestion."],
    ["dismissed", null, "You dismissed this suggestion."],
    ["modified", "Review · Place value", "You changed this to: Review · Place value."],
  ] as const)("a %s suggestion shows its outcome and offers no buttons", (status, summary, line) => {
    render(
      <RecommendationCard
        recommendation={{ ...BASE, status, modifiedActionSummary: summary }}
        onAccept={vi.fn()}
        onDismiss={vi.fn()}
        onModify={vi.fn()}
      />,
    );
    expect(screen.getByText(line)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("while saving, the buttons are disabled so a double tap cannot send two decisions", () => {
    render(<RecommendationCard recommendation={BASE} isSaving onAccept={vi.fn()} onDismiss={vi.fn()} onModify={vi.fn()} />);
    for (const name of ["Accept", "Modify", "Dismiss"]) {
      expect(screen.getByRole("button", { name })).toBeDisabled();
    }
  });

  it("a watch-list suggestion with no skill is titled by its type, with its own source label (D41)", () => {
    render(
      <RecommendationCard
        recommendation={{
          ...BASE,
          kind: "monitor_progress",
          targetSkillDisplayName: "",
          targetSkillId: null,
          sourceLabel: "Based on recent learning activity",
        }}
        onAccept={vi.fn()}
        onDismiss={vi.fn()}
        onModify={vi.fn()}
      />,
    );
    expect(screen.getByText("Monitor Progress")).toBeInTheDocument();
    expect(screen.getByText("Based on recent learning activity")).toBeInTheDocument();
    expect(screen.queryByText("Based on practice activity")).not.toBeInTheDocument();
  });

  it("shows a save error as an alert", () => {
    render(<RecommendationCard recommendation={BASE} errorMessage="This suggestion was already decided." onAccept={vi.fn()} onDismiss={vi.fn()} onModify={vi.fn()} />);
    expect(screen.getByRole("alert")).toHaveTextContent("This suggestion was already decided.");
  });

  it('renders no "Accept all" control', () => {
    render(<RecommendationCard recommendation={BASE} onAccept={vi.fn()} onDismiss={vi.fn()} onModify={vi.fn()} />);
    expect(screen.queryByText(/accept all/i)).not.toBeInTheDocument();
  });
});
