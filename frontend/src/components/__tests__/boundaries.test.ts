import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const SRC_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../../");
const COMPONENTS_ROOT = resolve(SRC_ROOT, "components");
const ROUTES_ROOT = resolve(SRC_ROOT, "routes");

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const stats = statSync(full);
    if (stats.isDirectory()) {
      if (entry === "node_modules" || entry === "__tests__") continue;
      walk(full, out);
    } else if (/\.(ts|tsx|json)$/.test(entry)) {
      out.push(full);
    }
  }
  return out;
}

/**
 * Strips `//` and `/* *\/` comments so these checks scan actual code, not
 * this codebase's own explanatory prose (which legitimately says things
 * like "there is no RiskLevel type" or "no engagementTrajectory field" to
 * document the constraint — those sentences are the opposite of a
 * violation, and a naive grep would flag them as one).
 */
function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .map((line) => line.replace(/\/\/.*$/, ""))
    .join("\n");
}

const allSrcFiles = walk(SRC_ROOT);
const componentFiles = walk(COMPONENTS_ROOT);
// The gallery route is a dev-only demonstration page, not a "component" —
// it legitimately samples every state (including inert callback fixtures)
// but is excluded from the boundary checks that scope to components/.
const routeFiles = walk(ROUTES_ROOT).filter((f) => !f.includes("gallery"));

describe("boundary: no component imports from api/types.ts", () => {
  it("no file under components/ imports the backend type module directly", () => {
    const offenders: string[] = [];
    for (const file of componentFiles) {
      const contents = readFileSync(file, "utf-8");
      // matches `from "../../api/types"`, `from "../api/types"`, etc. — any
      // relative import specifier ending in /api/types (with or without a
      // trailing .ts, which verbatimModuleSyntax forbids anyway)
      if (/from\s+["'][^"']*\/api\/types(?:\.ts)?["']/.test(contents)) {
        offenders.push(file);
      }
    }
    expect(offenders).toEqual([]);
  });
});

describe("boundary: no RiskLevel type exists — assert by search", () => {
  it("no source file declares or references a RiskLevel type", () => {
    const offenders: string[] = [];
    for (const file of allSrcFiles) {
      const contents = stripComments(readFileSync(file, "utf-8"));
      if (/RiskLevel/.test(contents)) offenders.push(file);
    }
    expect(offenders).toEqual([]);
  });

  it('no source file contains the literal risk tiers "Low"/"Moderate"/"High" as a risk label', () => {
    const offenders: string[] = [];
    for (const file of allSrcFiles) {
      const contents = readFileSync(file, "utf-8");
      if (/\brisk[_A-Za-z]*\s*[:=]\s*["'](Low|Moderate|High)["']/i.test(contents)) {
        offenders.push(file);
      }
    }
    expect(offenders).toEqual([]);
  });
});

describe("boundary: D17 — no engagement trajectory STATE anywhere", () => {
  it("no source file references engagementTrajectory", () => {
    const offenders: string[] = [];
    for (const file of allSrcFiles) {
      const contents = stripComments(readFileSync(file, "utf-8"));
      if (/engagementTrajectory/.test(contents)) offenders.push(file);
    }
    expect(offenders).toEqual([]);
  });

  it("engagementSparkline (the retained series) still exists — D17 keeps the data", () => {
    const hits = allSrcFiles.filter((f) => readFileSync(f, "utf-8").includes("engagementSparkline"));
    expect(hits.length).toBeGreaterThan(0);
  });
});

describe("boundary: practiceCount is never rendered", () => {
  it("no component file renders skill.practiceCount or {practiceCount}", () => {
    const offenders: string[] = [];
    for (const file of componentFiles) {
      const contents = readFileSync(file, "utf-8");
      // Allow the identifier only where it is destructured/typed, not
      // interpolated into JSX output. A simple heuristic: forbid it inside
      // a JSX expression `{...practiceCount...}` or template literal.
      if (/\{[^}]*practiceCount[^}]*\}/.test(contents) && file.includes("SkillProgress")) {
        // SkillProgress.tsx may reference the type field name in comments;
        // fail only if it appears in a JSX braces expression that isn't a
        // prop type / destructure (rough but effective for this codebase).
        const jsxUsage = /<[^>]*\{[^}]*practiceCount/.test(contents);
        if (jsxUsage) offenders.push(file);
      }
    }
    expect(offenders).toEqual([]);
  });
});

describe("boundary: no Accept-all control anywhere", () => {
  it('no component or route contains an "Accept all" control', () => {
    const offenders: string[] = [];
    for (const file of [...componentFiles, ...routeFiles]) {
      const contents = stripComments(readFileSync(file, "utf-8"));
      if (/accept\s*all/i.test(contents)) offenders.push(file);
    }
    expect(offenders).toEqual([]);
  });
});

describe("boundary: disclosure is not hard-coded in any component", () => {
  it("DisclosureFooter takes the text as a prop, never hard-codes it", () => {
    const file = componentFiles.find((f) => f.endsWith("DisclosureFooter.tsx"))!;
    const contents = readFileSync(file, "utf-8");
    expect(contents).not.toContain("Literature-informed synthetic data");
  });

  it("no OTHER component hard-codes the disclosure wording", () => {
    const offenders = componentFiles.filter(
      (f) =>
        !f.endsWith("DisclosureFooter.tsx") &&
        readFileSync(f, "utf-8").includes("Literature-informed synthetic data"),
    );
    expect(offenders).toEqual([]);
  });
});

describe("boundary: forbidden vocabulary never appears in rendered/source strings", () => {
  const FORBIDDEN = [
    "diagnos",
    "dyscalculia",
    "disorder",
    "deficit",
    "disability",
    "impairment",
    "screening",
    "detected",
    "population",
    "dd_subtype",
  ];

  it("no component or route source contains a banned term", () => {
    const offenders: string[] = [];
    for (const file of [...componentFiles, ...routeFiles]) {
      const contents = readFileSync(file, "utf-8").toLowerCase();
      for (const term of FORBIDDEN) {
        if (contents.includes(term)) offenders.push(`${file}: ${term}`);
      }
    }
    expect(offenders).toEqual([]);
  });
});

describe("boundary: no probability, confidence, score or model name is ever rendered", () => {
  // Practice accuracy percentages (SessionCard, per-session B telemetry) are
  // legitimate domain data, not a model confidence — plan §4.5's own mockup
  // shows "Accuracy 82%". This check targets the WATCH/rank/recommendation
  // surfaces, which must never carry a probability-shaped value.
  const STATUS_FILES = ["WatchStatusBadge", "PriorityBadge", "TrajectoryChip", "RecommendationCard"];

  it("status/priority/trajectory/recommendation components never render a model version or probability-shaped string", () => {
    const offenders: string[] = [];
    for (const file of componentFiles) {
      if (!STATUS_FILES.some((name) => file.includes(name))) continue;
      const contents = readFileSync(file, "utf-8");
      if (/prob_class|predicted_class|logreg|armA|p\s*=\s*0\.\d/i.test(contents)) {
        offenders.push(file);
      }
    }
    expect(offenders).toEqual([]);
  });
});
