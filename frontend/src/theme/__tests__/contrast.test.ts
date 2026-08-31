import { describe, expect, it } from "vitest";
import { colors } from "../tokens";

// WCAG relative luminance / contrast ratio (https://www.w3.org/TR/WCAG21/#dfn-relative-luminance).
function relativeLuminance(hex: string): number {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16) / 255;
  const g = parseInt(h.slice(2, 4), 16) / 255;
  const b = parseInt(h.slice(4, 6), 16) / 255;
  const f = (c: number) => (c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}

function contrastRatio(a: string, b: string): number {
  const l1 = relativeLuminance(a);
  const l2 = relativeLuminance(b);
  const [hi, lo] = l1 > l2 ? [l1, l2] : [l2, l1];
  return (hi + 0.05) / (lo + 0.05);
}

const AA_NORMAL_TEXT = 4.5;
const AA_LARGE_TEXT_OR_UI = 3;

// Every text/background pair actually used for meaningful text in this
// app's restyled components (Step 8 report has the full narrative;
// this is the automated version of that same table).
const TEXT_PAIRS: { name: string; fg: string; bg: string; min: number }[] = [
  { name: "ink.primary / background", fg: colors.textPrimary, bg: colors.background, min: AA_NORMAL_TEXT },
  { name: "ink.primary / surface1", fg: colors.textPrimary, bg: colors.surface1, min: AA_NORMAL_TEXT },
  { name: "ink.secondary / background", fg: colors.textSecondary, bg: colors.background, min: AA_NORMAL_TEXT },
  { name: "ink.secondary / surface1", fg: colors.textSecondary, bg: colors.surface1, min: AA_NORMAL_TEXT },
  {
    name: "watch.watching.fg / watch.watching.bg",
    fg: colors.watchWatchingFg,
    bg: colors.watchWatchingBg,
    min: AA_NORMAL_TEXT,
  },
  {
    name: "watch.noConcern.fg / watch.noConcern.bg",
    fg: colors.watchNoConcernFg,
    bg: colors.watchNoConcernBg,
    min: AA_NORMAL_TEXT,
  },
  {
    name: "watch.gettingStarted.fg / watch.gettingStarted.bg",
    fg: colors.watchGettingStartedFg,
    bg: colors.watchGettingStartedBg,
    min: AA_NORMAL_TEXT,
  },
  { name: "foreground / primary (CTA text)", fg: colors.foreground, bg: colors.primary, min: AA_NORMAL_TEXT },
  { name: "foreground / danger.soft (Dismiss/Reject text)", fg: colors.foreground, bg: colors.dangerSoft, min: AA_NORMAL_TEXT },
  { name: "dangerText / surface1 (inline form error)", fg: colors.dangerText, bg: colors.surface1, min: AA_NORMAL_TEXT },
  { name: "surface1 / foreground (dark button text)", fg: colors.surface1, bg: colors.foreground, min: AA_NORMAL_TEXT },
];

// Non-text graphical objects (icons, focus outlines, progress-bar fills) —
// WCAG 1.4.11 sets a lower 3:1 bar for these, not 4.5:1.
const GRAPHICAL_PAIRS: { name: string; fg: string; bg: string; min: number }[] = [
  { name: "foreground bar fill / surface2 track", fg: colors.foreground, bg: colors.surface2, min: AA_LARGE_TEXT_OR_UI },
];

describe("Step 8: WCAG AA contrast — every text/background pair in the theme layer", () => {
  it.each(TEXT_PAIRS)("$name meets 4.5:1", ({ fg, bg, min, name }) => {
    const ratio = contrastRatio(fg, bg);
    expect(ratio, `${name} measured ${ratio.toFixed(2)}:1, needs >= ${min}:1`).toBeGreaterThanOrEqual(
      min,
    );
  });

  it.each(GRAPHICAL_PAIRS)("$name (non-text UI) meets 3:1", ({ fg, bg, min, name }) => {
    const ratio = contrastRatio(fg, bg);
    expect(ratio, `${name} measured ${ratio.toFixed(2)}:1, needs >= ${min}:1`).toBeGreaterThanOrEqual(
      min,
    );
  });

  it("documents that textMuted FAILS AA — this is expected, not a bug (see tokens.ts)", () => {
    const ratio = contrastRatio(colors.textMuted, colors.background);
    expect(ratio).toBeLessThan(AA_NORMAL_TEXT);
  });

  it("documents that primaryForeground (white on primary) FAILS AA for normal text — never use it for text", () => {
    const ratio = contrastRatio(colors.primaryForeground, colors.primary);
    expect(ratio).toBeLessThan(AA_NORMAL_TEXT);
  });

  it("documents that dangerForeground (white on danger) FAILS AA for normal text — never use it for text", () => {
    const ratio = contrastRatio(colors.dangerForeground, colors.danger);
    expect(ratio).toBeLessThan(AA_NORMAL_TEXT);
  });

  it("documents that focusRing FAILS the 3:1 non-text threshold against background/surface1 (ported as-is, flagged)", () => {
    expect(contrastRatio(colors.focusRing, colors.background)).toBeLessThan(AA_LARGE_TEXT_OR_UI);
    expect(contrastRatio(colors.focusRing, colors.surface1)).toBeLessThan(AA_LARGE_TEXT_OR_UI);
  });
});
