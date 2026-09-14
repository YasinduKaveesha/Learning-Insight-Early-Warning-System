import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DisclosureFooter } from "../shared/DisclosureFooter";
import { FramingLine } from "../shared/FramingLine";

describe("FramingLine", () => {
  it('renders the EXACT required wording, no paraphrase', () => {
    render(<FramingLine />);
    expect(
      screen.getByText("The system flags learners for teacher review."),
    ).toBeInTheDocument();
  });
});

describe("DisclosureFooter", () => {
  it("renders whatever text is passed as the disclosure prop", () => {
    render(<DisclosureFooter disclosure="Literature-informed synthetic data — not clinical evidence." />);
    expect(
      screen.getByText("Literature-informed synthetic data — not clinical evidence."),
    ).toBeInTheDocument();
  });

  it("renders a DIFFERENT string too — proving the text comes from the prop, not a constant", () => {
    render(<DisclosureFooter disclosure="Some other disclosure text entirely." />);
    expect(screen.getByText("Some other disclosure text entirely.")).toBeInTheDocument();
  });
});
