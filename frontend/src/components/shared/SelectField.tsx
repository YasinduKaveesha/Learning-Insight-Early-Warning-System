import { Check, ChevronDown } from "lucide-react";
import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";

/** Gap between the field and its list, matching the 4px the list used to hard-code. */
const GAP = 4;
/** Never let the list touch the edge of the screen. */
const EDGE = 8;
/** The height the list would like, when the room is there. */
const PREFERRED_MAX = 256;
/** Below this there is no point flipping -- show a stub and let it scroll. */
const MIN_HEIGHT = 96;

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: readonly SelectOption[];
  /** The first entry, shown when nothing is chosen ("Choose a suggestion").
   * It carries the empty value, so a caller can tell "not chosen" from a real
   * choice and disable whatever the choice feeds. */
  placeholder: string;
  disabled?: boolean;
}

/**
 * A labelled dropdown whose OPEN LIST is part of the page.
 *
 * WHY THIS IS NOT A `<select>`. It was one, and a native select's open list is
 * an operating-system window: no CSS reaches it, so it arrived as a white
 * panel with a bright blue highlight that belonged to Windows rather than to
 * this dashboard, and looked different again on every platform. Styling it at
 * all means drawing it ourselves.
 *
 * WHAT THAT COSTS, AND WHAT IS PAID BACK HERE. A native select carries keyboard
 * and screen-reader behaviour for free; a `<div>` carries none, and most
 * hand-built dropdowns quietly lose it. This one implements the WAI-ARIA
 * combobox/listbox pattern rather than approximating it:
 *
 *   - the trigger is `role="combobox"` with `aria-expanded`, `aria-controls`
 *     and `aria-activedescendant`, labelled by the visible label;
 *   - the list is `role="listbox"`, each row `role="option"` with
 *     `aria-selected`;
 *   - focus STAYS on the trigger while the list is open, and the active row is
 *     named by `aria-activedescendant` -- which is what lets a screen reader
 *     announce each row as the arrows move without the focus ring jumping;
 *   - Enter, Space, Alt+Down and the arrows open it; arrows move; Enter or
 *     Space chooses; Escape closes and returns nothing; Home and End jump;
 *     typing a letter jumps to the next row starting with it, as a native
 *     select does;
 *   - a click anywhere outside closes it.
 *
 * The chosen row is marked with a tick AND a tinted background, never colour
 * alone.
 */
export function SelectField({
  label,
  value,
  onChange,
  options,
  placeholder,
  disabled = false,
}: SelectFieldProps) {
  const baseId = useId();
  const listId = `${baseId}-list`;
  const labelId = `${baseId}-label`;
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [isOpen, setIsOpen] = useState(false);
  /** Which way the list opens, and how tall it may be -- both measured, never assumed. */
  const [placement, setPlacement] = useState<"down" | "up">("down");
  const [maxHeight, setMaxHeight] = useState<number | null>(null);

  // The placeholder is a real row, so "back to no choice" stays reachable.
  const items: SelectOption[] = [{ value: "", label: placeholder }, ...options];
  const selectedIndex = Math.max(
    items.findIndex((o) => o.value === value),
    0,
  );
  const [activeIndex, setActiveIndex] = useState(selectedIndex);
  const activeId = `${baseId}-option-${activeIndex}`;
  const isPlaceholder = value === "";

  function open(startAt = selectedIndex) {
    if (disabled) return;
    setActiveIndex(startAt);
    setIsOpen(true);
  }

  function close() {
    setIsOpen(false);
    triggerRef.current?.focus();
  }

  function choose(index: number) {
    const item = items[index];
    if (item === undefined) return;
    onChange(item.value);
    setIsOpen(false);
    triggerRef.current?.focus();
  }

  /**
   * DECIDE WHICH WAY TO OPEN, BY MEASURING.
   *
   * The list used to be pinned below the field. On a field low in the card -- the Skill field on a
   * phone, say -- that ran the list off the bottom of the screen: the last rows were cut in half or
   * out of sight entirely, and internal scrolling did not help because the box ITSELF was off
   * screen.
   *
   * So: open downward when the list fits there, and flip upward when it does not. Flipping
   * unconditionally would only move the problem -- a field near the top of the screen would be
   * clipped the other way -- so the side with more room wins when neither fits. The height is
   * capped to the room actually available, so the list is never taller than the space it has.
   *
   * useLayoutEffect, not useEffect: this runs before the browser paints, so the list never appears
   * in the wrong place and jumps.
   */
  useLayoutEffect(() => {
    if (!isOpen) return;

    function measure() {
      const trigger = triggerRef.current;
      const list = listRef.current;
      if (!trigger || !list) return;

      const rect = trigger.getBoundingClientRect();
      const viewport = window.innerHeight || document.documentElement.clientHeight;
      const roomBelow = viewport - rect.bottom - GAP - EDGE;
      const roomAbove = rect.top - GAP - EDGE;
      // Half the viewport, or PREFERRED_MAX, whichever is smaller -- the old cap, kept.
      const cap = Math.min(PREFERRED_MAX, Math.round(viewport / 2));
      // scrollHeight is the list's natural height, even while it is capped.
      const natural = list.scrollHeight;

      const next = natural <= roomBelow || roomBelow >= roomAbove ? "down" : "up";
      setPlacement(next);
      setMaxHeight(Math.max(MIN_HEIGHT, Math.min(cap, next === "down" ? roomBelow : roomAbove)));
    }

    measure();
    // The room available changes under the list while it is open.
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [isOpen]);

  // Keep the active row in view when the arrows walk past the visible area.
  useEffect(() => {
    if (!isOpen) return;
    const row = listRef.current?.querySelector(`#${CSS.escape(activeId)}`);
    // Guarded: jsdom (and older browsers) do not implement scrollIntoView, and
    // keeping a row in view is a nicety -- it must never break the dropdown.
    if (row instanceof HTMLElement && typeof row.scrollIntoView === "function") {
      row.scrollIntoView({ block: "nearest" });
    }
  }, [isOpen, activeId]);

  // A click anywhere else closes the list -- including on another dropdown,
  // so two can never be open at once.
  useEffect(() => {
    if (!isOpen) return;
    function onPointerDown(event: MouseEvent) {
      if (!wrapperRef.current?.contains(event.target as Node)) setIsOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [isOpen]);

  /** Type-ahead: jump to the next row starting with the typed letter. */
  function jumpToLetter(letter: string) {
    const lower = letter.toLowerCase();
    const from = isOpen ? activeIndex + 1 : selectedIndex + 1;
    for (let step = 0; step < items.length; step += 1) {
      const index = (from + step) % items.length;
      if (items[index]?.label.toLowerCase().startsWith(lower)) {
        if (isOpen) setActiveIndex(index);
        else choose(index);
        return;
      }
    }
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLButtonElement>) {
    if (disabled) return;

    if (!isOpen) {
      if (["Enter", " ", "ArrowDown", "ArrowUp"].includes(event.key)) {
        event.preventDefault();
        open();
        return;
      }
    } else {
      switch (event.key) {
        case "Escape":
          event.preventDefault();
          close();
          return;
        case "Enter":
        case " ":
          event.preventDefault();
          choose(activeIndex);
          return;
        case "ArrowDown":
          event.preventDefault();
          setActiveIndex((i) => Math.min(i + 1, items.length - 1));
          return;
        case "ArrowUp":
          event.preventDefault();
          setActiveIndex((i) => Math.max(i - 1, 0));
          return;
        case "Home":
          event.preventDefault();
          setActiveIndex(0);
          return;
        case "End":
          event.preventDefault();
          setActiveIndex(items.length - 1);
          return;
        case "Tab":
          // Leaving the field abandons the list rather than choosing blindly.
          setIsOpen(false);
          return;
        default:
          break;
      }
    }

    if (event.key.length === 1 && /\S/.test(event.key)) {
      event.preventDefault();
      jumpToLetter(event.key);
    }
  }

  return (
    <div className="flex flex-col gap-1" ref={wrapperRef}>
      <span id={labelId} className="text-sm font-medium text-ink-primary">
        {label}
      </span>
      <div className="relative">
        <button
          ref={triggerRef}
          type="button"
          role="combobox"
          aria-controls={listId}
          aria-expanded={isOpen}
          aria-haspopup="listbox"
          aria-labelledby={`${labelId} ${baseId}-value`}
          aria-activedescendant={isOpen ? activeId : undefined}
          disabled={disabled}
          onClick={() => (isOpen ? setIsOpen(false) : open())}
          onKeyDown={onKeyDown}
          /* text-base, not text-sm: a control under 16px makes iOS Safari zoom
             the whole page on focus, which on a 375px screen throws the card
             off-screen mid-edit. */
          className={`flex min-h-[44px] w-full items-center justify-between gap-2 rounded-lg border border-border-strong bg-surface1 px-3 text-left text-base focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring disabled:opacity-40 ${
            isPlaceholder ? "text-ink-secondary" : "text-ink-primary"
          }`}
        >
          <span id={`${baseId}-value`} className="truncate">
            {items[selectedIndex]?.label ?? placeholder}
          </span>
          <ChevronDown
            aria-hidden="true"
            size={20}
            className={`shrink-0 text-ink-secondary transition-transform ${isOpen ? "rotate-180" : ""}`}
          />
        </button>

        {isOpen ? (
          <ul
            ref={listRef}
            id={listId}
            role="listbox"
            aria-labelledby={labelId}
            tabIndex={-1}
            data-placement={placement}
            style={{
              maxHeight: maxHeight ?? undefined,
              ...(placement === "down"
                ? { top: `calc(100% + ${GAP}px)` }
                : { bottom: `calc(100% + ${GAP}px)` }),
            }}
            className="absolute left-0 right-0 z-30 overflow-y-auto rounded-lg border border-border-strong bg-surface1 py-1 shadow-lg"
          >
            {items.map((option, index) => {
              const isSelected = option.value === value;
              const isActive = index === activeIndex;
              return (
                <li
                  key={option.value || "__placeholder"}
                  id={`${baseId}-option-${index}`}
                  role="option"
                  aria-selected={isSelected}
                  // onMouseDown, not onClick: mousedown fires before the
                  // outside-click handler closes the list and takes the row
                  // out from under the pointer.
                  onMouseDown={(e) => {
                    e.preventDefault();
                    choose(index);
                  }}
                  onMouseEnter={() => setActiveIndex(index)}
                  className={`flex min-h-[44px] cursor-pointer items-center justify-between gap-2 px-3 text-base ${
                    isActive ? "bg-suggestionPurple-bg" : ""
                  } ${isSelected ? "font-semibold text-ink-primary" : "text-ink-primary"} ${
                    index === 0 && option.value === "" ? "text-ink-secondary" : ""
                  }`}
                >
                  <span className="truncate">{option.label}</span>
                  {/* A tick as well as the tint: the chosen row is never
                      signalled by colour alone. */}
                  {isSelected ? (
                    <Check
                      aria-hidden="true"
                      size={18}
                      className="shrink-0 text-suggestionPurple-accept"
                    />
                  ) : null}
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>
    </div>
  );
}
