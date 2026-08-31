import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// Hardening pass: "the page body never scrolls sideways at any width" (plan
// §8) needs verifying at the LAYOUT level, not just hidden behind
// `body { overflow-x: hidden }`. jsdom cannot measure real rendered widths,
// so this is a static guard: no component/route may declare a fixed pixel
// width wider than the 375px design floor without a responsive guard
// (min-w-[44px] touch targets and the max-w-[480px]/[1200px]/[375px]
// content wrappers are the known-safe exceptions). A NEW arbitrary width
// like `w-[500px]` landing here — unlike `max-w`, which caps rather than
// forces — would be exactly the kind of change that only shows up on a
// real narrow viewport, which is what this test exists to catch before
// that happens.
const SRC_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../../");
const SCAN_ROOTS = ["components", "routes"];

// Allowed: min-width (a floor, never causes overflow) and max-width (a
// cap). Forbidden: a bare fixed `w-[...]` that FORCES an element to a pixel
// width regardless of viewport.
const FORCED_WIDTH_PATTERN = /(?<!min-|max-)\bw-\[\d+(?:\.\d+)?(?:px|rem)\]/g;

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const stats = statSync(full);
    if (stats.isDirectory()) {
      if (entry === "node_modules" || entry === "__tests__") continue;
      walk(full, out);
    } else if (/\.(ts|tsx)$/.test(entry)) {
      out.push(full);
    }
  }
  return out;
}

describe("Step 8/hardening: no unguarded forced pixel width that could overflow 375px", () => {
  it("no component or route declares a bare w-[Npx] utility (only min-w-[...] / max-w-[...] are allowed)", () => {
    const offenders: string[] = [];
    for (const root of SCAN_ROOTS) {
      for (const file of walk(resolve(SRC_ROOT, root))) {
        const contents = readFileSync(file, "utf-8");
        const matches = contents.match(FORCED_WIDTH_PATTERN);
        if (matches) offenders.push(`${file}: ${matches.join(", ")}`);
      }
    }
    expect(offenders).toEqual([]);
  });
});
