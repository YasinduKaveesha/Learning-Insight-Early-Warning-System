import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DeleteClassDialog } from "../class/DeleteClassDialog";

function renderDialog(overrides: Partial<Parameters<typeof DeleteClassDialog>[0]> = {}) {
  const props = {
    isOpen: true,
    className: "Grade 2A",
    onConfirm: vi.fn().mockResolvedValue(undefined),
    onCancel: vi.fn(),
    ...overrides,
  };
  render(<DeleteClassDialog {...props} />);
  return props;
}

describe("DeleteClassDialog — two steps", () => {
  it("first asks whether the teacher is sure, centred over a blurred page", () => {
    renderDialog();
    const dialog = screen.getByRole("dialog", { name: "Delete “Grade 2A”?" });
    expect(screen.getByText(/Are you sure you want to delete this class\?/)).toBeInTheDocument();
    expect(dialog.parentElement!.className).toMatch(/items-center/);
    expect(dialog.parentElement!.className).toMatch(/justify-center/);
    expect(dialog.parentElement!.className).toMatch(/backdrop-blur/);
    // Step 2's field is not reachable yet.
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("No on step 1 cancels and deletes nothing", async () => {
    const props = renderDialog();
    await userEvent.click(screen.getByRole("button", { name: "No" }));
    expect(props.onCancel).toHaveBeenCalled();
    expect(props.onConfirm).not.toHaveBeenCalled();
  });

  it("Yes on step 1 does not delete -- it asks for the class name, which it shows", async () => {
    const props = renderDialog();
    await userEvent.click(screen.getByRole("button", { name: "Yes" }));
    expect(props.onConfirm).not.toHaveBeenCalled();
    expect(screen.getByLabelText(/to confirm/)).toHaveFocus();
    expect(screen.getByText("“Grade 2A”", { selector: "span" })).toBeInTheDocument();
  });

  it("the second Delete stays disabled until the name matches exactly, case included", async () => {
    const props = renderDialog();
    await userEvent.click(screen.getByRole("button", { name: "Yes" }));
    const field = screen.getByLabelText(/to confirm/);
    const confirm = screen.getByRole("button", { name: "Delete" });

    for (const wrong of ["grade 2a", "Grade 2", "Grade 2AB"]) {
      await userEvent.clear(field);
      await userEvent.type(field, wrong);
      expect(confirm).toBeDisabled();
    }
    await userEvent.clear(field);
    await userEvent.type(field, "Grade 2A");
    expect(confirm).toBeEnabled();
    await userEvent.click(confirm);
    expect(props.onConfirm).toHaveBeenCalledWith("Grade 2A");
  });

  it("both steps share one grid cell, so the panel keeps the same size", async () => {
    renderDialog();
    const dialog = screen.getByRole("dialog");
    const cells = dialog.querySelectorAll(".col-start-1.row-start-1");
    expect(cells).toHaveLength(2);
    expect(cells[1]!.className).toMatch(/invisible/);
    await userEvent.click(screen.getByRole("button", { name: "Yes" }));
    expect(cells[0]!.className).toMatch(/invisible/);
    expect(cells[1]!.className).not.toMatch(/invisible/);
  });

  it("a failed delete shows an error and stays open for another try", async () => {
    renderDialog({ onConfirm: vi.fn().mockRejectedValue(new Error("HTTP 503")) });
    await userEvent.click(screen.getByRole("button", { name: "Yes" }));
    await userEvent.type(screen.getByLabelText(/to confirm/), "Grade 2A");
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("Couldn't delete this class."),
    );
    expect(screen.queryByText(/503/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete" })).toBeEnabled();
  });
});
