import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// textMuted (#9398a1) measures ~2.6:1 against background — fails WCAG AA's
// 4.5:1 for text (see src/theme/tokens.ts's header and the Step 8 report's
// contrast table). It must not be used for any meaningful text anywhere in
// the app. The Tailwind classes it would surface as are `text-ink-muted`
// (component source) or `ink.muted` (raw token reference).
const SRC_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../../");
const SCAN_ROOTS = ["components", "routes"];

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

describe("Step 8: textMuted / ink.muted is never used for text", () => {
  it("no component or route file references the ink-muted / text-muted class", () => {
    const offenders: string[] = [];
    for (const root of SCAN_ROOTS) {
      for (const file of walk(resolve(SRC_ROOT, root))) {
        const contents = readFileSync(file, "utf-8");
        if (/\btext-ink-muted\b/.test(contents) || /\btextMuted\b/.test(contents)) {
          offenders.push(file);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
