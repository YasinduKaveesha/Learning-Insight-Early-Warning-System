import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// Plan §10: no fixture, source file, or user-facing string may carry these.
const AUDIT_ONLY_TERMS = ["population", "dd_subtype"];

const FORBIDDEN_LANGUAGE = [
  "diagnos",
  "dyscalculia",
  "disorder",
  "deficit",
  "disability",
  "impairment",
  "screening",
  "detected",
];

const SRC_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../../");

// Test files legitimately name these terms (to assert their absence
// elsewhere) — excluded by the *.test.ts suffix, not by skipping __tests__/
// wholesale, so every fixture (including every __tests__/*.json) and every
// non-test source file still gets scanned.
const TEST_FILE_PATTERN = /\.test\.tsx?$/;

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const stats = statSync(full);
    if (stats.isDirectory()) {
      if (entry === "node_modules") continue;
      walk(full, out);
    } else if (/\.(ts|tsx|json)$/.test(entry) && !TEST_FILE_PATTERN.test(entry)) {
      out.push(full);
    }
  }
  return out;
}

function allSourceFiles(): string[] {
  return walk(SRC_ROOT);
}

describe("forbidden terms scan", () => {
  it("no source file contains population or dd_subtype", () => {
    const offenders: string[] = [];
    for (const file of allSourceFiles()) {
      const contents = readFileSync(file, "utf-8");
      for (const term of AUDIT_ONLY_TERMS) {
        if (contents.toLowerCase().includes(term)) {
          offenders.push(`${file}: "${term}"`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it("no source file contains diagnostic/clinical language", () => {
    const offenders: string[] = [];
    for (const file of allSourceFiles()) {
      const contents = readFileSync(file, "utf-8").toLowerCase();
      for (const term of FORBIDDEN_LANGUAGE) {
        if (contents.includes(term)) {
          offenders.push(`${file}: "${term}"`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
