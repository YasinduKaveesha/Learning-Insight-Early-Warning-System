import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// Step 8: "a test should assert no raw hex appears in component source."
// Scoped to components/ and routes/ (component source) — theme/tokens.ts
// and tailwind.config.js are the two files ALLOWED to hold hex literals;
// they are the semantic layer everything else must route through.
const SRC_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../../");
const SCAN_ROOTS = ["components", "routes"];
const HEX_PATTERN = /#[0-9a-fA-F]{3,8}\b/g;

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

describe("theme: no raw hex colour in component/route source", () => {
  it("no file under components/ or routes/ contains a hex colour literal", () => {
    const offenders: string[] = [];
    for (const root of SCAN_ROOTS) {
      for (const file of walk(resolve(SRC_ROOT, root))) {
        const contents = readFileSync(file, "utf-8");
        const matches = contents.match(HEX_PATTERN);
        if (matches) offenders.push(`${file}: ${matches.join(", ")}`);
      }
    }
    expect(offenders).toEqual([]);
  });
});
