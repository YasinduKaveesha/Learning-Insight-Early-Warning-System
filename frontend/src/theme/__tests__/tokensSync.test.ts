import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { colors } from "../tokens";

// tokens.ts and tailwind.config.js are two physical files that must behave
// as ONE semantic layer (Step 8: "define the semantic layer on top in ONE
// place"). This test is what enforces that — it extracts every hex literal
// from tailwind.config.js and asserts each one used there also appears
// somewhere in tokens.ts's colors object, so the pair can never silently
// drift apart.
const TAILWIND_CONFIG_PATH = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../../tailwind.config.js",
);

describe("theme tokens — tailwind.config.js and tokens.ts stay in sync", () => {
  const configSource = readFileSync(TAILWIND_CONFIG_PATH, "utf-8");
  const hexInConfig = [...configSource.matchAll(/#[0-9a-fA-F]{6}\b/g)].map((m) =>
    m[0].toLowerCase(),
  );
  const hexInTokens = new Set(Object.values(colors).map((v) => v.toLowerCase()));

  it("tailwind.config.js declares at least the full palette", () => {
    expect(hexInConfig.length).toBeGreaterThanOrEqual(20);
  });

  it("every hex value in tailwind.config.js also appears in tokens.ts", () => {
    const missing = [...new Set(hexInConfig)].filter((hex) => !hexInTokens.has(hex));
    expect(missing).toEqual([]);
  });

  it("every hex value in tokens.ts also appears in tailwind.config.js", () => {
    const configHexSet = new Set(hexInConfig);
    const missing = [...hexInTokens].filter((hex) => !configHexSet.has(hex));
    expect(missing).toEqual([]);
  });
});
