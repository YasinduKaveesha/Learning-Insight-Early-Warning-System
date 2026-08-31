import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ClassKeyDisplay } from "../class/ClassKeyDisplay";

describe("ClassKeyDisplay", () => {
  it("the aria-label reads the key character by character", () => {
    render(<ClassKeyDisplay classKey="7K4P92" />);
    expect(screen.getByLabelText("7 K 4 P 9 2")).toBeInTheDocument();
  });

  it("renders the key large and monospaced by default (the primary-element size)", () => {
    const { container } = render(<ClassKeyDisplay classKey="7K4P92" />);
    const keyEl = screen.getByText("7K4P92");
    expect(keyEl.className).toMatch(/font-mono/);
    expect(keyEl.className).toMatch(/text-3xl/);
    expect(container.textContent).toContain("7K4P92");
  });

  it("the compact size still spells the key out identically", () => {
    render(<ClassKeyDisplay classKey="9M3R58" size="compact" />);
    expect(screen.getByLabelText("9 M 3 R 5 8")).toBeInTheDocument();
    expect(screen.getByText("9M3R58")).toBeInTheDocument();
  });

  it("has no control that implies the key can be regenerated (D1: permanent)", () => {
    render(<ClassKeyDisplay classKey="7K4P92" />);
    expect(screen.queryByText(/regenerate/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/new key/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/reset/i)).not.toBeInTheDocument();
  });

  it("copying the key shows a confirmation", async () => {
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
    render(<ClassKeyDisplay classKey="7K4P92" />);
    await userEvent.click(screen.getByRole("button", { name: "Copy key" }));
    expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
  });
});
