import { act, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { SWIPE_AUTO_CLOSE_MS, SWIPE_REVEAL_PX, SWIPE_SLIDE_MS, SwipeToDelete } from "../class/SwipeToDelete";

function Harness({ onDelete = vi.fn(), onCardClick = vi.fn() }) {
  const [isOpen, setIsOpen] = useState(false);
  return (
    <SwipeToDelete isOpen={isOpen} onOpenChange={setIsOpen} onDelete={onDelete} label="2A">
      <button type="button" onClick={onCardClick}>
        2A card
      </button>
    </SwipeToDelete>
  );
}

function swipe(card: HTMLElement, dx: number, dy = 0) {
  fireEvent.pointerDown(card, { pointerId: 1, clientX: 200, clientY: 100, button: 0, pointerType: "touch" });
  fireEvent.pointerMove(card, { pointerId: 1, clientX: 200 + dx / 2, clientY: 100 + dy / 2, pointerType: "touch" });
  fireEvent.pointerMove(card, { pointerId: 1, clientX: 200 + dx, clientY: 100 + dy, pointerType: "touch" });
  fireEvent.pointerUp(card, { pointerId: 1, clientX: 200 + dx, clientY: 100 + dy, pointerType: "touch" });
}

describe("SwipeToDelete", () => {
  it("at rest the card is in place and the red Delete layer is hidden", () => {
    render(<Harness />);
    const card = screen.getByTestId("swipe-card");
    expect(card.style.transform).toBe("translateX(0px)");
    expect(card.previousElementSibling!.className).toMatch(/invisible/);
    expect(card.previousElementSibling!.className).toMatch(/bg-danger/);
  });

  it("swiping left past halfway slides the card over and uncovers Delete", () => {
    render(<Harness />);
    const card = screen.getByTestId("swipe-card");
    swipe(card, -80);
    expect(card.style.transform).toBe(`translateX(-${SWIPE_REVEAL_PX}px)`);
    expect(screen.getByRole("button", { name: "Delete 2A" })).toBeInTheDocument();
  });

  it("a short swipe springs back", () => {
    render(<Harness />);
    const card = screen.getByTestId("swipe-card");
    swipe(card, -30);
    expect(card.style.transform).toBe("translateX(0px)");
  });

  it("swiping right does nothing", () => {
    render(<Harness />);
    const card = screen.getByTestId("swipe-card");
    swipe(card, 80);
    expect(card.style.transform).toBe("translateX(0px)");
  });

  it("a mostly vertical movement is a scroll, not a swipe", () => {
    render(<Harness />);
    const card = screen.getByTestId("swipe-card");
    swipe(card, -40, 90);
    expect(card.style.transform).toBe("translateX(0px)");
  });

  it("letting go after a swipe does not also open the card", () => {
    const onCardClick = vi.fn();
    render(<Harness onCardClick={onCardClick} />);
    const card = screen.getByTestId("swipe-card");
    swipe(card, -80);
    fireEvent.click(screen.getByText("2A card"));
    expect(onCardClick).not.toHaveBeenCalled();
  });

  it("tapping an open card closes it instead of opening it; a plain tap opens it", () => {
    const onCardClick = vi.fn();
    render(<Harness onCardClick={onCardClick} />);
    const card = screen.getByTestId("swipe-card");
    swipe(card, -80);
    fireEvent.click(screen.getByText("2A card")); // the mouse's release click: ignored
    expect(card.style.transform).toBe(`translateX(-${SWIPE_REVEAL_PX}px)`);
    fireEvent.pointerDown(card, { pointerId: 2, clientX: 150, clientY: 100, button: 0 });
    fireEvent.pointerUp(card, { pointerId: 2, clientX: 150, clientY: 100 });
    fireEvent.click(screen.getByText("2A card")); // a real tap: closes the open card
    expect(card.style.transform).toBe("translateX(0px)");
    expect(onCardClick).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("2A card"));
    expect(onCardClick).toHaveBeenCalledTimes(1);
  });

  it("the uncovered Delete calls onDelete", () => {
    const onDelete = vi.fn();
    render(<Harness onDelete={onDelete} />);
    swipe(screen.getByTestId("swipe-card"), -80);
    fireEvent.click(screen.getByRole("button", { name: "Delete 2A" }));
    expect(onDelete).toHaveBeenCalledTimes(1);
  });

  it("an open card slides back by itself after 1 second", () => {
    vi.useFakeTimers();
    try {
      render(<Harness />);
      const card = screen.getByTestId("swipe-card");
      swipe(card, -80);
      expect(SWIPE_AUTO_CLOSE_MS).toBe(1000);
      act(() => vi.advanceTimersByTime(SWIPE_AUTO_CLOSE_MS - 50));
      expect(card.style.transform).toBe(`translateX(-${SWIPE_REVEAL_PX}px)`);
      act(() => vi.advanceTimersByTime(50));
      expect(card.style.transform).toBe("translateX(0px)");
    } finally {
      vi.useRealTimers();
    }
  });

  it("the red layer stays while the card slides back, and hides when the slide ends", () => {
    render(<Harness />);
    const card = screen.getByTestId("swipe-card");
    const underlay = card.previousElementSibling!;
    swipe(card, -80);
    fireEvent.pointerDown(card, { pointerId: 2, clientX: 150, clientY: 100, button: 0 });
    fireEvent.pointerUp(card, { pointerId: 2, clientX: 150, clientY: 100 });
    fireEvent.click(screen.getByText("2A card")); // close it
    expect(card.style.transform).toBe("translateX(0px)");
    expect(card.style.transition).toBe(`transform ${SWIPE_SLIDE_MS}ms ease-out`);
    expect(underlay.className).not.toMatch(/invisible/);
    fireEvent.transitionEnd(card);
    expect(underlay.className).toMatch(/invisible/);
  });
});
