import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SelectField } from "../shared/SelectField";

const OPTIONS = [
  { value: "counting", label: "Counting" },
  { value: "addition", label: "Addition" },
  { value: "subtraction", label: "Subtraction" },
];

function renderField(value = "", onChange = vi.fn()) {
  render(
    <SelectField
      label="Skill"
      value={value}
      onChange={onChange}
      options={OPTIONS}
      placeholder="No specific skill"
    />,
  );
  return { onChange, trigger: screen.getByRole("combobox", { name: /skill/i }) };
}

describe("SelectField — the list is part of the page, so it must behave like one", () => {
  it("is closed to begin with, showing the placeholder", () => {
    const { trigger } = renderField();
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(trigger).toHaveTextContent("No specific skill");
  });

  it("opens on click and lists the placeholder plus every option", async () => {
    const { trigger } = renderField();
    await userEvent.click(trigger);

    const list = screen.getByRole("listbox");
    const names = within(list)
      .getAllByRole("option")
      .map((o) => o.textContent);
    expect(names).toEqual(["No specific skill", "Counting", "Addition", "Subtraction"]);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
  });

  it("reports the chosen value and closes", async () => {
    const { onChange, trigger } = renderField();
    await userEvent.click(trigger);
    await userEvent.click(screen.getByRole("option", { name: "Addition" }));

    expect(onChange).toHaveBeenCalledWith("addition");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("lets a teacher go back to no choice at all", async () => {
    const { onChange, trigger } = renderField("addition");
    await userEvent.click(trigger);
    await userEvent.click(screen.getByRole("option", { name: "No specific skill" }));
    expect(onChange).toHaveBeenCalledWith("");
  });

  it("marks the chosen row with aria-selected AND a tick, never colour alone", async () => {
    const { trigger } = renderField("addition");
    await userEvent.click(trigger);

    const chosen = screen.getByRole("option", { name: /Addition/ });
    expect(chosen).toHaveAttribute("aria-selected", "true");
    expect(chosen.querySelector("svg")).not.toBeNull();
    expect(screen.getByRole("option", { name: "Counting" })).toHaveAttribute(
      "aria-selected",
      "false",
    );
  });

  it("closes when the teacher clicks away, choosing nothing", async () => {
    const { onChange, trigger } = renderField();
    await userEvent.click(trigger);
    await userEvent.click(document.body);

    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });

  it("meets the 44px tap target, on the trigger and on every row", async () => {
    const { trigger } = renderField();
    expect(trigger.className).toContain("min-h-[44px]");
    await userEvent.click(trigger);
    for (const option of screen.getAllByRole("option")) {
      expect(option.className).toContain("min-h-[44px]");
    }
  });

  it("is at least 16px, so iOS does not zoom the page on focus", () => {
    const { trigger } = renderField();
    expect(trigger.className).toContain("text-base");
    expect(trigger.className).not.toContain("text-sm");
  });

  it("greys the placeholder but not a real choice", () => {
    const { unmount } = render(
      <SelectField
        label="Skill"
        value=""
        onChange={vi.fn()}
        options={OPTIONS}
        placeholder="No specific skill"
      />,
    );
    expect(screen.getByRole("combobox").className).toContain("text-ink-secondary");
    unmount();
    renderField("addition");
    expect(screen.getByRole("combobox").className).toContain("text-ink-primary");
  });

  it("can be disabled", async () => {
    render(
      <SelectField
        label="Skill"
        value=""
        onChange={vi.fn()}
        options={OPTIONS}
        placeholder="No specific skill"
        disabled
      />,
    );
    const trigger = screen.getByRole("combobox");
    expect(trigger).toBeDisabled();
    await userEvent.click(trigger);
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });
});

describe("SelectField — keyboard, which a hand-built dropdown usually loses", () => {
  it("opens with Enter, moves with the arrows and chooses with Enter", async () => {
    const { onChange, trigger } = renderField();
    trigger.focus();

    await userEvent.keyboard("{Enter}");
    expect(screen.getByRole("listbox")).toBeInTheDocument();

    await userEvent.keyboard("{ArrowDown}{ArrowDown}");
    await userEvent.keyboard("{Enter}");
    expect(onChange).toHaveBeenCalledWith("addition");
  });

  it("opens with ArrowDown and with Space", async () => {
    const { trigger } = renderField();
    trigger.focus();
    await userEvent.keyboard("{ArrowDown}");
    expect(screen.getByRole("listbox")).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");

    await userEvent.keyboard(" ");
    expect(screen.getByRole("listbox")).toBeInTheDocument();
  });

  it("Escape closes without choosing, and focus comes back to the field", async () => {
    const { onChange, trigger } = renderField();
    trigger.focus();
    await userEvent.keyboard("{ArrowDown}{ArrowDown}{Escape}");

    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
    expect(trigger).toHaveFocus();
  });

  it("Home and End jump to the ends", async () => {
    const { onChange, trigger } = renderField();
    trigger.focus();
    await userEvent.keyboard("{ArrowDown}{End}{Enter}");
    expect(onChange).toHaveBeenCalledWith("subtraction");
  });

  it("typing a letter jumps to that row, as a native select does", async () => {
    const { onChange, trigger } = renderField();
    trigger.focus();
    await userEvent.keyboard("{ArrowDown}");
    await userEvent.keyboard("s");
    await userEvent.keyboard("{Enter}");
    expect(onChange).toHaveBeenCalledWith("subtraction");
  });

  it("the arrows stop at the ends rather than wrapping past them", async () => {
    const { onChange, trigger } = renderField();
    trigger.focus();
    await userEvent.keyboard("{ArrowDown}{ArrowUp}{ArrowUp}{ArrowUp}{Enter}");
    expect(onChange).toHaveBeenCalledWith("");
  });

  it("names the active row for a screen reader, and only while open", async () => {
    const { trigger } = renderField();
    expect(trigger).not.toHaveAttribute("aria-activedescendant");

    trigger.focus();
    await userEvent.keyboard("{ArrowDown}{ArrowDown}");
    const active = trigger.getAttribute("aria-activedescendant");
    expect(active).toBeTruthy();
    expect(document.getElementById(active!)).toHaveTextContent("Counting");
  });

  it("keeps focus on the field while the list is open, per the combobox pattern", async () => {
    const { trigger } = renderField();
    trigger.focus();
    await userEvent.keyboard("{ArrowDown}");
    expect(trigger).toHaveFocus();
  });

  it("Tab leaves the field without choosing", async () => {
    const { onChange, trigger } = renderField();
    trigger.focus();
    await userEvent.keyboard("{ArrowDown}");
    await userEvent.tab();
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe("SelectField — which way the list opens is measured, not assumed", () => {
  const VIEWPORT = 600;

  /** Put the field at a given distance down the viewport, and give the list a natural height. */
  function placeField({ top, height = 44, listHeight = 320 }: {
    top: number;
    height?: number;
    listHeight?: number;
  }) {
    window.innerHeight = VIEWPORT;
    vi.spyOn(HTMLButtonElement.prototype, "getBoundingClientRect").mockReturnValue({
      top,
      bottom: top + height,
      left: 0,
      right: 200,
      width: 200,
      height,
      x: 0,
      y: top,
      toJSON: () => ({}),
    } as DOMRect);
    vi.spyOn(HTMLUListElement.prototype, "scrollHeight", "get").mockReturnValue(listHeight);
  }

  afterEach(() => vi.restoreAllMocks());

  it("opens DOWNWARD when there is room below", async () => {
    placeField({ top: 40 });
    const { trigger } = renderField();
    await userEvent.click(trigger);

    const list = screen.getByRole("listbox");
    expect(list).toHaveAttribute("data-placement", "down");
    expect(list.style.top).not.toBe("");
    expect(list.style.bottom).toBe("");
  });

  // THE REPORTED BUG: a field low in the card ran its list off the bottom of the
  // screen -- the last rows cut in half or out of sight, with internal scrolling
  // no help because the box itself was off screen.
  it("opens UPWARD when the list would run off the bottom", async () => {
    placeField({ top: 500 });
    const { trigger } = renderField();
    await userEvent.click(trigger);

    const list = screen.getByRole("listbox");
    expect(list).toHaveAttribute("data-placement", "up");
    expect(list.style.bottom).not.toBe("");
    expect(list.style.top).toBe("");
  });

  it("does not flip merely because the list is tall, if it still fits below", async () => {
    placeField({ top: 40, listHeight: 500 });
    const { trigger } = renderField();
    await userEvent.click(trigger);
    // 600 - 84 - 12 = 504 of room below; a 500px list fits.
    expect(screen.getByRole("listbox")).toHaveAttribute("data-placement", "down");
  });

  it("picks the roomier side when the list fits neither way", async () => {
    placeField({ top: 420, listHeight: 1000 });
    const { trigger } = renderField();
    await userEvent.click(trigger);
    // 136 below vs 408 above — up wins.
    expect(screen.getByRole("listbox")).toHaveAttribute("data-placement", "up");
  });

  it("never grows taller than the room it has", async () => {
    placeField({ top: 420, listHeight: 1000 });
    const { trigger } = renderField();
    await userEvent.click(trigger);

    const list = screen.getByRole("listbox");
    const capped = Number.parseInt(list.style.maxHeight, 10);
    expect(capped).toBeGreaterThan(0);
    expect(capped).toBeLessThanOrEqual(420 - 4 - 8);
  });

  it("still scrolls internally, so a long list stays reachable either way", async () => {
    placeField({ top: 500 });
    const { trigger } = renderField();
    await userEvent.click(trigger);
    expect(screen.getByRole("listbox").className).toContain("overflow-y-auto");
  });

  it("re-measures while open, because the room under it can change", async () => {
    placeField({ top: 40 });
    const { trigger } = renderField();
    await userEvent.click(trigger);
    expect(screen.getByRole("listbox")).toHaveAttribute("data-placement", "down");

    // The page scrolls and the field is now near the bottom.
    vi.restoreAllMocks();
    placeField({ top: 500 });
    window.dispatchEvent(new Event("resize"));

    await waitFor(() =>
      expect(screen.getByRole("listbox")).toHaveAttribute("data-placement", "up"),
    );
  });
});
