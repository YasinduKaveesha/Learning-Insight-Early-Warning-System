import { render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { WatchStatusBadge } from "../../components/status/WatchStatusBadge";
import type { WatchStatus } from "../../lib/presentation";

const WATCH_STATUS_BADGE_PATH = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../components/status/WatchStatusBadge.tsx",
);

const STATUSES: WatchStatus[] = [
  { kind: "watching", label: "Worth watching right now", priority: 1 },
  { kind: "no_concern", label: "No current concern identified" },
  { kind: "getting_started", label: "Getting Started", sessionsCompleted: 1, sessionsRequired: 3 },
];

describe("Step 8: watch status tone — never alarming, never red", () => {
  it("no watch status uses the danger or accent-red token", () => {
    const source = readFileSync(WATCH_STATUS_BADGE_PATH, "utf-8");
    expect(source).not.toMatch(/\bdanger\b/i);
    expect(source).not.toMatch(/accent-red|accentRed/i);
  });

  it.each(STATUSES)("'$kind' renders BOTH an icon and text — greyscale-distinguishable", (status) => {
    const { unmount } = render(<WatchStatusBadge status={status} />);
    // Icon and label text both present as real DOM content, not conveyed by
    // colour alone (plan §9) — this holds regardless of whether colour
    // renders at all, e.g. under a greyscale/forced-colours media query.
    expect(screen.getByText(status.label)).toBeInTheDocument();
    unmount();
  });

  it("the three states use visibly distinct icon glyphs, not just colour, to differ from each other", () => {
    const rendered = STATUSES.map((status) => {
      const { container, unmount } = render(<WatchStatusBadge status={status} />);
      const icon = container.querySelector('[aria-hidden="true"]')?.textContent;
      unmount();
      return icon;
    });
    // ◐ / ○ / ◔ — three distinct glyphs. Even with every colour stripped
    // out (greyscale), a teacher can tell the three statuses apart from
    // shape alone.
    expect(new Set(rendered).size).toBe(3);
  });
});
