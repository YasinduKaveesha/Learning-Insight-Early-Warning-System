#!/usr/bin/env node
// Author-time transform. Reads real ML artefacts from OUTSIDE the repo (or from the
// repo's own .gitignore'd notebooks/outputs/) and writes derived, filtered JSON
// fixtures into frontend/src/api/mock/fixtures/. Never run at app runtime.
//
// Usage: node scripts/build-fixtures.mjs
//
// Source artefacts (per plan/backend_plan.md §10):
//   57_test_predicted_probabilities.csv  — real per-(student,t) model predictions
//   55_worked_shap_explanation_example.csv, 54_shap_global_importance.csv — SHAP
//   dataset/training/training_table_seed20260828_n300_h5_sweepn4.csv — engineered features + evidence_status
//   56_early_detection_curve.csv — reports trend
//
// IMPORTANT: 57 carries an audit-only cohort column ("population") and every
// probability column (prob_class_0/1/2+, predicted_class, actual_class). Rule 3-F1
// forbids the cohort label from reaching any fixture; probabilities never reach the
// browser at all (plan §5, §7). Both are read here ONLY to derive watchFlag / rank,
// then dropped before anything is written to disk.

import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const DOCS_ROOT = resolve(__dirname, "../../../"); // "...Componant 3 -Teachers Dashboard/"
const REPO_ROOT = resolve(__dirname, "../../"); // "...Learning-Insight-Early-Warning-System/"
const FIXTURES_DIR = resolve(__dirname, "../src/api/mock/fixtures");

const PATHS = {
  predictions: resolve(
    REPO_ROOT,
    "notebooks/outputs/tables/57_test_predicted_probabilities.csv",
  ),
  shapWorked: resolve(
    REPO_ROOT,
    "notebooks/outputs/tables/55_worked_shap_explanation_example.csv",
  ),
  shapGlobal: resolve(
    REPO_ROOT,
    "notebooks/outputs/tables/54_shap_global_importance.csv",
  ),
  earlyDetection: resolve(
    REPO_ROOT,
    "notebooks/outputs/tables/56_early_detection_curve.csv",
  ),
  trainingTable: resolve(
    DOCS_ROOT,
    "dataset/training/training_table_seed20260828_n300_h5_sweepn4.csv",
  ),
};

for (const [name, path] of Object.entries(PATHS)) {
  try {
    readFileSync(path);
  } catch {
    console.error(`STOP: artefact "${name}" not found on disk at:\n  ${path}`);
    process.exit(1);
  }
}

// --- minimal CSV parser (handles the one quoted, comma-containing field in 55) ---
function parseCSV(text) {
  const rows = [];
  let row = [];
  let field = "";
  let inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"' && text[i + 1] === '"') {
        field += '"';
        i++;
      } else if (c === '"') {
        inQuotes = false;
      } else {
        field += c;
      }
    } else if (c === '"') {
      inQuotes = true;
    } else if (c === ",") {
      row.push(field);
      field = "";
    } else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(field);
      if (row.length > 1 || row[0] !== "") rows.push(row);
      row = [];
      field = "";
    } else {
      field += c;
    }
  }
  if (field !== "" || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  const header = rows[0];
  return rows.slice(1).map((r) => Object.fromEntries(header.map((h, i) => [h, r[i]])));
}

function readCSV(path) {
  return parseCSV(readFileSync(path, "utf-8"));
}

const num = (v) => (v === undefined || v === "" ? null : Number(v));

// ---------------------------------------------------------------------------
// Load real artefacts
// ---------------------------------------------------------------------------

const predictionsRaw = readCSV(PATHS.predictions);
const trainingRaw = readCSV(PATHS.trainingTable);
const shapGlobalRaw = readCSV(PATHS.shapGlobal).map((r) => {
  // header row is ",mean_abs_shap" — the feature name column has no header text
  const key = Object.keys(r)[0];
  return { feature: r[key], meanAbsShap: num(r.mean_abs_shap) };
});
const earlyDetectionRaw = readCSV(PATHS.earlyDetection);

console.log(`Loaded ${predictionsRaw.length} prediction rows (57)`);
console.log(`Loaded ${trainingRaw.length} training-table rows`);
console.log(`Loaded ${shapGlobalRaw.length} SHAP global importance rows (54)`);
console.log(`Loaded ${earlyDetectionRaw.length} early-detection curve rows (56)`);

// DROPPED from every fixture, per rule 3-F1 and plan §7: audit cohort label
// ("population"), every probability column, and predicted_class/actual_class.
// Read here only to derive watchFlag / rank; never written out.
const trainingByKey = new Map(trainingRaw.map((r) => [`${r.student_id}|${r.t}`, r]));

// ---------------------------------------------------------------------------
// Explanation sentence bank — built from the real global SHAP driver ranking
// (54) and the tone of the one real worked example (55), translated to
// display names. Time-index features are excluded entirely (filter #1,
// plan §7): is_first_snapshot, sessions_observed, and any lag/rollmean/delta
// variant of them.
// ---------------------------------------------------------------------------

const TIME_INDEX_BASE_FEATURES = new Set(["is_first_snapshot", "sessions_observed"]);

function baseFeatureName(name) {
  return name
    .replace(/_lag1$/, "")
    .replace(/_delta1$/, "")
    .replace(/_rollmean_prior$/, "")
    .replace(/_x_.*/, "");
}

// Server-supplied display names (plan §6.4 rule 3: no raw feature names ever
// reach an explanation). Hand-mapped from the base feature vocabulary that
// appears in the real SHAP ranking (54) and the feature register.
const DISPLAY_NAME = {
  error_recurrence_rate: "repeated errors on the same type of question",
  number_sense_mastery: "number sense mastery",
  stagnant_skill_count: "the number of skills that have stopped improving",
  hint_intensity: "how often hints are being used",
  score_avg_recent: "recent practice accuracy",
  engagement_decline_rate: "game engagement",
  mastery_progression_rate: "the pace of skill mastery",
  score_trend_slope: "the trend in practice accuracy",
  weakest_skill_persistence: "how long the weakest skill has stayed weak",
  frustration_mean: "frustration during game sessions",
  frustration_slope: "the trend in frustration during game sessions",
  rt_variability: "how consistent response times are",
  difficulty_floor_hits: "how often the easiest difficulty level is used",
  guess_guard_rate: "guessing rather than attempting a question",
  hint_avoidance: "avoiding hints even when stuck",
  engagement_consistency: "how consistent game engagement is",
};

// Contribution-framed (never causal, plan §6.4 rule 4), never protective.
const SENTENCE_TEMPLATE = {
  error_recurrence_rate:
    "the same type of question is being answered incorrectly across recent sessions",
  number_sense_mastery: "number sense has not progressed across recent sessions",
  stagnant_skill_count: "several skills have not improved across recent sessions",
  hint_intensity: "hints are being used heavily relative to recent practice",
  score_avg_recent: "recent practice accuracy has been low",
  engagement_decline_rate: "game engagement has been declining across recent sessions",
  mastery_progression_rate: "skill mastery has slowed across recent sessions",
  score_trend_slope: "practice accuracy has not improved across recent sessions",
  weakest_skill_persistence: "the weakest skill has stayed weak for several sessions",
  frustration_mean: "frustration has been elevated during recent game sessions",
  frustration_slope: "frustration has been rising during recent game sessions",
  guess_guard_rate: "recent answers show signs of guessing rather than attempting",
  hint_avoidance: "hints are being avoided even when the learner appears stuck",
};

const TOP_DRIVERS = shapGlobalRaw
  .map((r) => baseFeatureName(r.feature))
  .filter((base) => !TIME_INDEX_BASE_FEATURES.has(base))
  .filter((base) => SENTENCE_TEMPLATE[base])
  .filter((base, i, arr) => arr.indexOf(base) === i) // dedupe, keep global rank order
  .slice(0, 8);

console.log(`Built explanation sentence bank from ${TOP_DRIVERS.length} real top drivers:`);
console.log(`  ${TOP_DRIVERS.join(", ")}`);

// Drivers whose template sentence would contradict a trajectory chip that is
// independently computed and displayed alongside the explanation — e.g. never
// say "game engagement has been declining" beside a chip reading "improving".
const DRIVER_TRAJECTORY_GUARD = {
  score_trend_slope: "practiceTrajectory",
  mastery_progression_rate: "practiceTrajectory",
  score_avg_recent: "practiceTrajectory",
  engagement_decline_rate: "engagementTrajectory",
};

function buildExplanation(studentId, t, watchFlag, practiceState, engagementState) {
  if (!watchFlag) return null;
  const trajectoryState = { practiceTrajectory: practiceState, engagementTrajectory: engagementState };
  const eligibleDrivers = TOP_DRIVERS.filter((driver) => {
    const guard = DRIVER_TRAJECTORY_GUARD[driver];
    if (!guard) return true;
    // Only usable when the guarded trajectory is not itself "improving" —
    // a declining-sounding sentence must never sit beside an improving chip.
    return trajectoryState[guard] !== "improving";
  });
  if (eligibleDrivers.length === 0) return null;

  // Deterministic pick so the same (student, t) always gets the same sentence.
  const seed = hashString(`${studentId}|${t}`);
  const primary = eligibleDrivers[seed % eligibleDrivers.length];
  const secondary =
    eligibleDrivers.length > 1
      ? eligibleDrivers[(seed + 1) % eligibleDrivers.length]
      : null;
  const sentence = secondary
    ? `${capitalise(SENTENCE_TEMPLATE[primary])}, and ${SENTENCE_TEMPLATE[secondary]}.`
    : `${capitalise(SENTENCE_TEMPLATE[primary])}.`;
  if (sentence.length > 280) {
    return sentence.slice(0, 277) + "...";
  }
  return sentence;
}

function hashString(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return h;
}

function capitalise(s) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

// ---------------------------------------------------------------------------
// Trajectory — OLS-slope-threshold rule from backend_plan.md §6.3 (D11),
// applied to the closest available real analogue for each source:
//   practice_accuracy  ← score_trend_slope   (ε = 0.05)
//   game_engagement    ← engagement_decline_rate (ε = 0.010, SIGN INVERTED:
//                          a rising decline rate is worsening engagement)
//
// AMBIGUITY FLAGGED IN REPORT: backend_plan.md D17 says engagement_trajectory
// is computed but must NEVER be served to any client — it is held back due to
// a measured inversion on the DD subgroup. frontend_plan.md §4.4's mockup and
// api/types.ts (already shipped in Step 2) both require an engagementTrajectory
// on every LearnerSnapshot. This fixture computes it from real data so the
// Step-2 type contract has something to render, but the D17/frontend_plan
// conflict is unresolved — see the Step 3 report.
// ---------------------------------------------------------------------------

function slopeToTrajectoryState(slope, epsilon, sessionsCompleted, invert = false) {
  if (slope === null || sessionsCompleted < 4) return "unknown";
  const s = invert ? -slope : slope;
  if (s > epsilon) return "improving";
  if (s < -epsilon) return "needs_attention";
  return "stable";
}

// ---------------------------------------------------------------------------
// Build one LearnerSnapshot per (student, t) from real predictions + training
// table. watchFlag / rank derived here from predicted_class / prob_class_2plus,
// both of which are then DROPPED — they never appear in the emitted fixture.
// ---------------------------------------------------------------------------

const CURRENT_T = 7; // see report: chosen for a realistic watch/no-concern mix

const byT = new Map();
for (const row of predictionsRaw) {
  const t = Number(row.t);
  if (!byT.has(t)) byT.set(t, []);
  byT.get(t).push(row);
}

function buildSnapshotsAtT(t) {
  const rows = byT.get(t) ?? [];
  // Rank by prob_class_2plus desc, WITHIN this t only (never pooled, plan §6.2).
  const flaggedSorted = rows
    .filter((r) => r.predicted_class !== "0")
    .slice()
    .sort((a, b) => Number(b["prob_class_2+"]) - Number(a["prob_class_2+"]));
  const rankByStudent = new Map(flaggedSorted.map((r, i) => [r.student_id, i + 1]));

  return rows.map((r) => {
    const watchFlag = r.predicted_class !== "0";
    const sessionsCompleted = t; // real rows: sessions_observed === t (verified against training table)
    const training = trainingByKey.get(`${r.student_id}|${t}`);
    const practiceSlope = training ? num(training.score_trend_slope) : null;
    const engagementSlope = training ? num(training.engagement_decline_rate) : null;
    const practiceState = slopeToTrajectoryState(practiceSlope, 0.05, sessionsCompleted);
    const engagementState = slopeToTrajectoryState(
      engagementSlope,
      0.01,
      sessionsCompleted,
      true,
    );

    return {
      studentId: r.student_id,
      sessionNumber: t,
      watchFlag,
      rankWithinSnapshot: rankByStudent.get(r.student_id) ?? null,
      evidenceStatus: "sufficient_evidence",
      sessionsCompleted,
      practiceTrajectory: { source: "practice_accuracy", state: practiceState },
      engagementTrajectory: { source: "game_engagement", state: engagementState },
      explanation: buildExplanation(
        r.student_id,
        t,
        watchFlag,
        practiceState,
        engagementState,
      ),
      accuracySparkline: buildSparkline(r.student_id, t),
      // predicted_class, prob_class_0/1/2+, actual_class and population are
      // read above ONLY to compute watchFlag/rank/sentences. None are copied
      // into this object.
    };
  });
}

function buildSparkline(studentId, t) {
  const values = [];
  for (let s = 3; s <= t; s += 2) {
    const training = trainingByKey.get(`${studentId}|${s}`);
    const v = training ? num(training.score_avg_recent) : null;
    if (v !== null) values.push(Number(v.toFixed(3)));
  }
  return values.slice(-5);
}

const snapshotsAtCurrentT = buildSnapshotsAtT(CURRENT_T);
console.log(
  `t=${CURRENT_T}: ${snapshotsAtCurrentT.length} real students, ` +
    `${snapshotsAtCurrentT.filter((s) => s.watchFlag).length} flagged`,
);

// Find a real, still-flagged student who is improving on practice accuracy,
// for the two-signal path (plan §10 manual checklist).
const improvingButFlagged = snapshotsAtCurrentT.find(
  (s) => s.watchFlag && s.practiceTrajectory.state === "improving",
);
console.log(
  improvingButFlagged
    ? `Two-signal exemplar: ${improvingButFlagged.studentId} (improving practice accuracy, still flagged)`
    : "WARNING: no real improving-but-flagged student found at the chosen t",
);

// ---------------------------------------------------------------------------
// Skill progress — seven skills, frozen order, matching the seven
// `ipsatised_mastery_*` columns actually present in the research dataset
// (plan §5's "seven skills in frozen order").
//
// AMBIGUITY FLAGGED IN REPORT: the dataset has no per-skill slope or
// per-skill practice-opportunity count — only one per-student
// `mastery_progression_rate` and the per-skill `ipsatised_mastery_*` value
// at each t. `direction` here is derived from a REAL two-point delta
// (ipsatised value at t vs. t-2 for the same student) rather than invented,
// using an authored ε=0.01 threshold with no documented precedent — flagged.
// `practiceCount` has no real source at all and is an authored placeholder
// scaled from sessionsCompleted, clearly not derived from telemetry.
// ---------------------------------------------------------------------------

const SKILL_ORDER = [
  { skillId: "counting", displayName: "Counting", column: "ipsatised_mastery_counting" },
  {
    skillId: "number_sense",
    displayName: "Number sense",
    column: "ipsatised_mastery_number_sense",
  },
  {
    skillId: "place_value",
    displayName: "Place value",
    column: "ipsatised_mastery_place_value",
  },
  { skillId: "addition", displayName: "Addition", column: "ipsatised_mastery_addition" },
  {
    skillId: "subtraction",
    displayName: "Subtraction",
    column: "ipsatised_mastery_subtraction",
  },
  {
    skillId: "multiplication",
    displayName: "Multiplication",
    column: "ipsatised_mastery_multiplication",
  },
  { skillId: "division", displayName: "Division", column: "ipsatised_mastery_division" },
];

function buildSkillProgress(studentId, t) {
  const current = trainingByKey.get(`${studentId}|${t}`);
  const previous = trainingByKey.get(`${studentId}|${t - 2}`);
  if (!current) return null;
  return SKILL_ORDER.map(({ skillId, displayName, column }, i) => {
    const level = num(current[column]);
    const prevLevel = previous ? num(previous[column]) : null;
    let direction = "unknown";
    if (t >= 4) {
      if (level === null) direction = "unknown";
      else if (prevLevel === null) direction = "unknown";
      else direction = level - prevLevel > 0.01 ? "improving" : "not_moving";
    }
    return {
      skillId,
      displayName,
      direction,
      relativeLevel: level,
      practiceCount: Math.max(1, Math.round(t * (0.6 + 0.1 * i))), // authored placeholder — see report
    };
  });
}

// Per-skill min/max across the whole roster, used to bound the bar position
// (skillBarPositionFromBounds in lib/presentation.ts — see the doc comment
// there on why this can't be a single global 0-1 assumption).
function skillBounds(studentIds, t) {
  const bounds = {};
  for (const { skillId, column } of SKILL_ORDER) {
    let min = Infinity;
    let max = -Infinity;
    for (const id of studentIds) {
      const row = trainingByKey.get(`${id}|${t}`);
      const v = row ? num(row[column]) : null;
      if (v !== null) {
        min = Math.min(min, v);
        max = Math.max(max, v);
      }
    }
    bounds[skillId] = min <= max ? { min, max } : { min: -0.5, max: 0.5 };
  }
  return bounds;
}

// ---------------------------------------------------------------------------
// Early-warning trend (Reports) — direct transform of 56, no derivation needed.
// ---------------------------------------------------------------------------

const earlyWarningTrend = earlyDetectionRaw.map((r) => ({
  sessionNumber: Number(r.t),
  flagRate: Number(r.flag_rate),
  sampleSize: Number(r.n),
}));

// ---------------------------------------------------------------------------
// Write fixtures
// ---------------------------------------------------------------------------

mkdirSync(FIXTURES_DIR, { recursive: true });

function writeJSON(name, data) {
  const path = resolve(FIXTURES_DIR, name);
  writeFileSync(path, JSON.stringify(data, null, 2) + "\n");
  console.log(`Wrote ${name} (${Array.isArray(data) ? data.length + " rows" : "object"})`);
}

// A fixed, reproducible 24-student roster sampled from the 90 real students at
// t=7 (9 flagged incl. the two-signal exemplar, 15 not flagged) — realistic for
// three ~8-student classes on a 375px screen (plan §1's mobile-first target).
const watchedIds = snapshotsAtCurrentT.filter((s) => s.watchFlag).map((s) => s.studentId);
const calmIds = snapshotsAtCurrentT.filter((s) => !s.watchFlag).map((s) => s.studentId);
const exemplarId = improvingButFlagged?.studentId;
const pickedWatched = [
  exemplarId,
  ...watchedIds.filter((id) => id !== exemplarId),
].filter(Boolean).slice(0, 9);
const pickedCalm = calmIds.slice(0, 15);
const rosterIds = [...pickedWatched, ...pickedCalm];

const skillProgressByStudent = Object.fromEntries(
  rosterIds.map((id) => [id, buildSkillProgress(id, CURRENT_T)]),
);
const skillBoundsAtT = skillBounds(rosterIds, CURRENT_T);

writeJSON("realSnapshotsAtT7.json", snapshotsAtCurrentT);
writeJSON("earlyWarningTrend.json", earlyWarningTrend);
writeJSON("rosterStudentIds.json", rosterIds);
writeJSON("skillProgressByStudent.json", skillProgressByStudent);
writeJSON("skillBoundsAtT7.json", skillBoundsAtT);
writeJSON("twoSignalExemplarId.json", {
  studentId: exemplarId ?? null,
  sessionNumber: CURRENT_T,
});

console.log("\nDone. Hand-authored fixtures (classes, names, Getting Started student,");
console.log("session-gap examples) live in TypeScript alongside these — see");
console.log("src/api/mock/fixtures/authored.ts.");
