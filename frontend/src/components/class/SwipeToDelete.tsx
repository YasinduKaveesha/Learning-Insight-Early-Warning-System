import { Trash2 } from "lucide-react";
import { useEffect, useRef, useState, type PointerEvent, type ReactNode } from "react";

/** How far the card slides left to uncover the Delete action, in px. */
export const SWIPE_REVEAL_PX = 96;
/** How long an uncovered Delete stays open before the card slides back, in ms. */
export const SWIPE_AUTO_CLOSE_MS = 1000;
/** How long the card takes to slide open or back into place, in ms. */
export const SWIPE_SLIDE_MS = 350;
/** Movement before a press counts as a swipe (or a scroll) rather than a tap. */
const SWIPE_START_PX = 8;

export interface SwipeToDeleteProps {
  /** Whether the Delete action is uncovered. Owned by the parent so only one
   * card is ever open at a time. */
  isOpen: boolean;
  onOpenChange: (isOpen: boolean) => void;
  onDelete: () => void;
  /** Names the thing being deleted, for the Delete button's label. */
  label: string;
  children: ReactNode;
}

/**
 * Press, hold and swipe a card to the LEFT to uncover a red Delete action
 * underneath it (2026-09-14). The card keeps its size and simply slides; the
 * red layer is exactly the card's own shape behind it.
 *
 * - A vertical movement first is a scroll, and is left to the browser
 *   (`touch-action: pan-y`), so the page still scrolls through the cards.
 * - A tap that followed a swipe is swallowed, so letting go never also opens
 *   the class.
 * - Tapping an open card closes it instead of opening the class.
 * - Left alone, an open card slides back by itself after 1 s.
 */
export function SwipeToDelete({ isOpen, onOpenChange, onDelete, label, children }: SwipeToDeleteProps) {
  const start = useRef<{ x: number; y: number; id: number } | null>(null);
  const mode = useRef<"idle" | "swipe" | "scroll">("idle");
  const swallowClick = useRef(false);
  const [dragOffset, setDragOffset] = useState<number | null>(null);

  // Left open and untouched, the card slides back on its own. A new drag
  // (dragOffset set) holds it; letting go starts the 1 s again.
  // The latest callback is read through a ref: a parent passing a new arrow
  // function on every render must not keep restarting the countdown.
  const onOpenChangeRef = useRef(onOpenChange);
  onOpenChangeRef.current = onOpenChange;
  useEffect(() => {
    if (!isOpen || dragOffset !== null) return;
    const timer = setTimeout(() => onOpenChangeRef.current(false), SWIPE_AUTO_CLOSE_MS);
    return () => clearTimeout(timer);
  }, [isOpen, dragOffset]);

  const restingOffset = isOpen ? -SWIPE_REVEAL_PX : 0;
  const offset = dragOffset ?? restingOffset;

  // The red layer shows while the card is away from rest AND while it is still
  // sliding back -- hiding it the instant the card starts home would leave a
  // blank gap behind the slide. It is hidden once that slide has finished.
  const [isSlidingHome, setIsSlidingHome] = useState(false);
  useEffect(() => {
    if (offset !== 0) setIsSlidingHome(true);
  }, [offset]);
  const showUnderlay = offset !== 0 || isSlidingHome;

  function handlePointerDown(e: PointerEvent<HTMLDivElement>) {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    start.current = { x: e.clientX, y: e.clientY, id: e.pointerId };
    mode.current = "idle";
    swallowClick.current = false;
  }

  function handlePointerMove(e: PointerEvent<HTMLDivElement>) {
    const s = start.current;
    if (!s || s.id !== e.pointerId || mode.current === "scroll") return;
    const dx = e.clientX - s.x;
    const dy = e.clientY - s.y;
    if (mode.current === "idle") {
      if (Math.abs(dy) > SWIPE_START_PX && Math.abs(dy) > Math.abs(dx)) {
        mode.current = "scroll";
        return;
      }
      if (Math.abs(dx) <= SWIPE_START_PX) return;
      mode.current = "swipe";
      swallowClick.current = true;
      e.currentTarget.setPointerCapture?.(e.pointerId);
    }
    setDragOffset(Math.max(-SWIPE_REVEAL_PX, Math.min(0, restingOffset + dx)));
  }

  function handlePointerEnd(e: PointerEvent<HTMLDivElement>) {
    const s = start.current;
    if (!s || s.id !== e.pointerId) return;
    start.current = null;
    if (mode.current === "swipe" && dragOffset !== null) {
      // Past halfway stays open; short of it springs back.
      onOpenChange(dragOffset < -SWIPE_REVEAL_PX / 2);
    }
    mode.current = "idle";
    setDragOffset(null);
  }

  return (
    <div className="relative overflow-hidden rounded-lg">
      {/* The red layer under the card, the same shape as the card. Hidden while
          the card is at rest, so no red shows at its rounded corners. */}
      <div
        className={`absolute inset-0 flex justify-end rounded-lg bg-danger ${showUnderlay ? "" : "invisible"}`}
      >
        <button
          type="button"
          onClick={onDelete}
          aria-label={`Delete ${label}`}
          tabIndex={isOpen ? 0 : -1}
          aria-hidden={!isOpen}
          style={{ width: SWIPE_REVEAL_PX }}
          className="flex h-full flex-col items-center justify-center gap-1 text-foreground"
        >
          <Trash2 aria-hidden="true" size={22} strokeWidth={2.5} />
          <span className="text-sm font-bold">Delete</span>
        </button>
      </div>

      <div
        data-testid="swipe-card"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerEnd}
        onPointerCancel={handlePointerEnd}
        // A link is natively draggable with a mouse, which would steal the swipe.
        onDragStart={(e) => e.preventDefault()}
        onTransitionEnd={() => {
          if (offset === 0) setIsSlidingHome(false);
        }}
        onClickCapture={(e) => {
          if (swallowClick.current) {
            // The click a mouse fires on letting go of a swipe: ignore it
            // entirely, or it would close the card the swipe just opened.
            e.preventDefault();
            e.stopPropagation();
            swallowClick.current = false;
          } else if (isOpen) {
            e.preventDefault();
            e.stopPropagation();
            onOpenChange(false);
          }
        }}
        style={{
          transform: `translateX(${offset}px)`,
          transition: dragOffset === null ? `transform ${SWIPE_SLIDE_MS}ms ease-out` : "none",
          touchAction: "pan-y",
        }}
        className="relative select-none"
      >
        {children}
      </div>
    </div>
  );
}
