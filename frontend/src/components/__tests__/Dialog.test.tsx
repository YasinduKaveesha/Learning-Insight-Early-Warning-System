import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { Dialog } from "../shared/Dialog";

function Harness({ onClose }: { onClose: () => void }) {
  const [isOpen, setIsOpen] = useState(false);
  return (
    <div>
      <button type="button" onClick={() => setIsOpen(true)}>
        Open dialog
      </button>
      <Dialog
        isOpen={isOpen}
        onClose={() => {
          setIsOpen(false);
          onClose();
        }}
        titleId="test-dialog-title"
        title="Test Dialog"
      >
        <button type="button">First</button>
        <button type="button">Last</button>
      </Dialog>
    </div>
  );
}

describe("Dialog", () => {
  it("carries role=dialog and aria-labelledby pointing at the title", () => {
    render(<Dialog isOpen onClose={vi.fn()} titleId="t1" title="My Dialog">content</Dialog>);
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-labelledby", "t1");
    expect(screen.getByText("My Dialog")).toHaveAttribute("id", "t1");
  });

  it("closes on Escape", async () => {
    const onClose = vi.fn();
    render(<Dialog isOpen onClose={onClose} titleId="t1" title="My Dialog">content</Dialog>);
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });

  it("traps focus within the dialog on Tab from the last element", async () => {
    render(
      <Dialog isOpen onClose={vi.fn()} titleId="t1" title="My Dialog">
        <button type="button">First</button>
        <button type="button">Last</button>
      </Dialog>,
    );
    const last = screen.getByRole("button", { name: "Last" });
    last.focus();
    await userEvent.tab();
    // Focus should wrap back inside the dialog (to the close button or
    // "First"), never escape to document.body.
    expect(document.activeElement).not.toBe(document.body);
    expect(screen.getByRole("dialog").contains(document.activeElement)).toBe(true);
  });

  it("restores focus to the trigger on close", async () => {
    render(<Harness onClose={() => {}} />);
    const trigger = screen.getByRole("button", { name: "Open dialog" });
    await userEvent.click(trigger);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(document.activeElement).toBe(trigger);
  });
});
