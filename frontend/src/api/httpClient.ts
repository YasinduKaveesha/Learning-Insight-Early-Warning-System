// The real FastAPI client (frontend_plan §11, work order W4 / B6.3e-2).
//
// THIS IS THE ONLY PLACE backend JSON becomes a frontend shape. snake_case ->
// camelCase, nested -> flat, one call -> two: all of it happens here, so
// neither side's model bends toward the other. A screen never sees a backend
// field name.
//
// Three rules this file keeps, each for a reason that is easy to lose:
//
// 1. NEVER INVENT A VALUE. When the backend has no source for a field the
//    frontend type wants, the mapping sends the honest empty (null, [], or no
//    bar) rather than a plausible default. A made-up number a teacher acts on
//    is worse than a gap.
// 2. EVERY FAILURE REJECTS AS A PLAIN Error, so ErrorState renders. Nothing
//    throws synchronously.
// 3. The screens still re-apply sortCohortOrder / toWatchStatus /
//    filterExplanation. Nothing here relies on the backend's ordering.

import type {
  ApiClient,
  ClassReportsResponse,
  CohortResponse,
  CreateClassResult,
  StudentOverviewResponse,
  WatchListResponse,
} from "./client";
import type {
  EvidenceStatus,
  HomeSummary,
  LearnerSnapshot,
  SessionEntry,
  SkillProgress,
  TrajectoryState,
} from "./types";
import type { Grade, PendingRequestDisplay, RecommendationDisplay } from "../lib/presentation";
import { EARLY_WARNING_TREND_EXPLANATION } from "../lib/presentation";
import { supabase } from "./supabaseClient";

const API_BASE: string = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8100").replace(
  /\/$/,
  "",
);
const PREFIX = "/api/v1/t3";

// --- wire shapes (backend JSON, exactly as served) --------------------------

interface WireCard {
  student_id: string;
  display_name: string;
  classroom_id: string;
  t: number;
  evidence_status: EvidenceStatus;
  sessions_completed: number;
  watch_flag: boolean;
  rank_within_t: number | null;
  practice_trajectory: TrajectoryState;
  explanation: string | null;
  last_active_date: string | null;
  accuracy_sparkline: (number | null)[];
  engagement_sparkline: (number | null)[];
  model_version: string | null;
  inference_timestamp: string | null;
}

interface WireHome {
  disclosure: string;
  teacher_name: string | null;
  watch_count: number;
  active_students: number;
  class_count: number;
  getting_started_count: number;
  classes: {
    classroom_id: string;
    name: string | null;
    grade: Grade | null;
    learner_count: number;
    watch_count: number;
    getting_started_count: number;
    pending_request_count: number;
  }[];
}

interface WireCohort {
  disclosure: string;
  classroom_id: string;
  class_name: string | null;
  grade: Grade | null;
  class_key: string | null;
  pending_request_count: number;
  stats: { learner_count: number; watch_count: number; getting_started_count: number };
  learners: WireCard[];
}

interface WireWatch {
  disclosure: string;
  classroom_id: string | null;
  total_students: number;
  learners: WireCard[];
}

interface WireStudent {
  disclosure: string;
  student_id: string;
  display_name: string;
  classroom_id: string | null;
  class_name: string | null;
  t: number;
  evidence_status: EvidenceStatus;
  sessions_completed: number;
  watch_flag: boolean;
  rank_within_t: number | null;
  practice_trajectory: TrajectoryState;
  explanation: string | null;
}

interface WireSkills {
  skills: {
    skill: string;
    direction: TrajectoryState;
    practice_count: number;
    relative_level: number | null;
  }[];
}

interface WireSessions {
  sessions: {
    session_number: number;
    session_date: string | null;
    practice_present: boolean;
    games_present: boolean;
    practice: { accuracy_rate: number | null; hint_requests: number | null } | null;
    games: {
      learner_state: string | null;
      data_quality: "ok" | "technical_issue" | "incomplete_telemetry";
    } | null;
  }[];
}

interface WireReport {
  disclosure: string;
  class_name: string | null;
  early_warning_curve: { t: number; flag_rate: number }[];
  participation: { bucket_label: string; student_count: number }[];
}

// --- transport ---------------------------------------------------------------

async function get<T>(path: string): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (supabase) {
    const { data } = await supabase.auth.getSession();
    const token = data.session?.access_token;
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  // Bearer only, never a cookie: the API sets allow_credentials=False.
  const response = await fetch(`${API_BASE}${PREFIX}${path}`, { headers });
  if (!response.ok) {
    throw new Error(`Request to ${path} failed with HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

// --- mapping -----------------------------------------------------------------

/** Nulls in a sparkline are ABSENCES. They are dropped, never zero-filled: a
 * 0 would draw a bad session out of a missing one. */
function presentValues(values: (number | null)[]): number[] {
  return values.filter((v): v is number => v !== null);
}

function toSnapshot(card: WireCard): LearnerSnapshot {
  return {
    studentId: card.student_id,
    displayName: card.display_name,
    classId: card.classroom_id,
    sessionNumber: card.t,
    watchFlag: card.watch_flag,
    rankWithinSnapshot: card.rank_within_t,
    evidenceStatus: card.evidence_status,
    sessionsCompleted: card.sessions_completed,
    practiceTrajectory: { source: "practice_accuracy", state: card.practice_trajectory },
    explanation: card.explanation,
    // An empty string, not a made-up date: formatRelativeDate returns a
    // non-date input unchanged.
    lastActiveDate: card.last_active_date ?? "",
    accuracySparkline: presentValues(card.accuracy_sparkline),
    engagementSparkline: presentValues(card.engagement_sparkline),
    modelVersion: card.model_version ?? "",
    inferenceTimestamp: card.inference_timestamp ?? "",
  };
}

/**
 * Priority is a POSITION IN THE CLASS'S WATCH LIST (PriorityBadge: "position
 * within the list that produced it", rendered as "Priority N in <class>").
 *
 * The backend's rank_within_t is ranked across every scored learner at that
 * session in the whole pipeline run -- all 120 demo learners, not one class of
 * 20 -- so a learner can arrive as rank 100. Rendering "Priority 100 in 2A"
 * would state a quantity that does not exist. So, per class: flagged learners
 * ordered the way the backend orders a watch list, (t, rank), numbered 1..k.
 * Unflagged learners carry no priority.
 */
function renumberWithinClass(snapshots: LearnerSnapshot[]): LearnerSnapshot[] {
  const byClass = new Map<string, LearnerSnapshot[]>();
  for (const s of snapshots) {
    if (!s.watchFlag || s.rankWithinSnapshot === null) continue;
    const list = byClass.get(s.classId) ?? [];
    list.push(s);
    byClass.set(s.classId, list);
  }
  const positions = new Map<string, number>();
  for (const list of byClass.values()) {
    list
      .sort(
        (a, b) =>
          a.sessionNumber - b.sessionNumber ||
          (a.rankWithinSnapshot ?? 0) - (b.rankWithinSnapshot ?? 0),
      )
      .forEach((s, index) => positions.set(s.studentId, index + 1));
  }
  return snapshots.map((s) => ({ ...s, rankWithinSnapshot: positions.get(s.studentId) ?? null }));
}

const SKILL_DISPLAY_NAME: Record<string, string> = {
  counting: "Counting",
  number_sense: "Number sense",
  place_value: "Place value",
  addition: "Addition",
  subtraction: "Subtraction",
  multiplication: "Multiplication",
  division: "Division",
};
const SKILL_ORDER = Object.keys(SKILL_DISPLAY_NAME);

/** A skill is "not moving"; a trajectory is "stable". The two vocabularies
 * stay apart (frontend_plan §5). The skill vocabulary has no downward word, so
 * a falling skill slope is "not moving" -- never "improving". */
function toSkillDirection(direction: TrajectoryState): SkillProgress["direction"] {
  if (direction === "improving") return "improving";
  if (direction === "unknown") return "unknown";
  return "not_moving";
}

// --- the client ----------------------------------------------------------------

export class HttpClient implements ApiClient {
  async getHome(): Promise<HomeSummary> {
    const w = await get<WireHome>("/home");
    return {
      teacherName: w.teacher_name ?? "",
      studentsToWatch: w.watch_count,
      activeStudents: w.active_students,
      classCount: w.class_count,
      gettingStarted: w.getting_started_count,
      classes: w.classes.map((c) => ({
        classId: c.classroom_id,
        name: c.name ?? "",
        // classrooms.grade is required by D2 for every class the student app
        // creates; the null branch is type-level only.
        grade: c.grade ?? "GRADE_2",
        studentCount: c.learner_count,
        toWatchCount: c.watch_count,
        pendingRequestCount: c.pending_request_count,
      })),
      disclosure: w.disclosure,
    };
  }

  async getCohort(classId: string): Promise<CohortResponse> {
    const w = await get<WireCohort>(`/classes/${encodeURIComponent(classId)}/cohort`);
    return {
      classId: w.classroom_id,
      className: w.class_name ?? "",
      studentCount: w.stats.learner_count,
      toWatchCount: w.stats.watch_count,
      gettingStartedCount: w.stats.getting_started_count,
      pendingRequestCount: w.pending_request_count,
      students: renumberWithinClass(w.learners.map(toSnapshot)),
      disclosure: w.disclosure,
      grade: w.grade ?? "GRADE_2",
      // Empty only when no key has been minted (backend/scripts/mint_class_keys.py).
      classKey: w.class_key ?? "",
    };
  }

  async getClassWatchList(classId: string): Promise<WatchListResponse> {
    const w = await get<WireWatch>(`/classes/${encodeURIComponent(classId)}/watch`);
    return {
      totalStudents: w.total_students,
      disclosure: w.disclosure,
      students: renumberWithinClass(w.learners.map(toSnapshot)),
    };
  }

  async getWatchList(): Promise<WatchListResponse> {
    const w = await get<WireWatch>("/watch");
    return {
      totalStudents: w.total_students,
      disclosure: w.disclosure,
      students: renumberWithinClass(w.learners.map(toSnapshot)),
    };
  }

  async getStudentOverview(studentId: string): Promise<StudentOverviewResponse> {
    const id = encodeURIComponent(studentId);
    const [detail, skills] = await Promise.all([
      get<WireStudent>(`/students/${id}`),
      get<WireSkills>(`/students/${id}/skills`),
    ]);

    // Priority is class-relative (see renumberWithinClass), so it needs the
    // class's watch list; the detail endpoint's rank is run-wide.
    let priority: number | null = null;
    if (detail.watch_flag && detail.classroom_id) {
      const list = await this.getClassWatchList(detail.classroom_id);
      priority =
        list.students.find((s) => s.studentId === detail.student_id)?.rankWithinSnapshot ?? null;
    }

    const snapshot: LearnerSnapshot = {
      studentId: detail.student_id,
      displayName: detail.display_name,
      classId: detail.classroom_id ?? "",
      sessionNumber: detail.t,
      watchFlag: detail.watch_flag,
      rankWithinSnapshot: priority,
      evidenceStatus: detail.evidence_status,
      sessionsCompleted: detail.sessions_completed,
      practiceTrajectory: { source: "practice_accuracy", state: detail.practice_trajectory },
      explanation: detail.explanation,
      // Not rendered on the student screen, and not on StudentDetail.
      lastActiveDate: "",
      accuracySparkline: [],
      engagementSparkline: [],
      modelVersion: "",
      inferenceTimestamp: "",
    };

    return {
      snapshot,
      skills: skills.skills
        .slice()
        .sort((a, b) => SKILL_ORDER.indexOf(a.skill) - SKILL_ORDER.indexOf(b.skill))
        .map((s) => ({
          skillId: s.skill,
          displayName: SKILL_DISPLAY_NAME[s.skill] ?? s.skill,
          direction: toSkillDirection(s.direction),
          // Always null today (§8.5: the scale is undocumented), so the screen
          // draws no bar rather than a flat one.
          relativeLevel: s.relative_level,
          practiceCount: s.practice_count,
        })),
      disclosure: detail.disclosure,
      className: detail.class_name ?? "",
      skillBounds: {},
    };
  }

  async getStudentSessions(studentId: string): Promise<SessionEntry[]> {
    const w = await get<WireSessions>(`/students/${encodeURIComponent(studentId)}/sessions`);
    return w.sessions.map((s) => ({
      sessionNumber: s.session_number,
      date: s.session_date ?? "",
      practice: {
        present: s.practice_present,
        accuracy: s.practice?.accuracy_rate ?? null,
        pace: null, // D28: needs a class-wide baseline, gated by D16
        hintsUsed: s.practice?.hint_requests ?? null,
      },
      games: {
        present: s.games_present,
        dataComplete: (s.games?.data_quality ?? "ok") === "ok",
        state: s.games?.learner_state ?? null,
        // No served source yet -- QUESTIONS_FOR_ML_TEAM_3 Q5.
        stateReason: null,
        engagementDriver: null,
        frustrationDriver: null,
      },
    }));
  }

  getStudentRecommendations(_studentId: string): Promise<RecommendationDisplay[]> {
    // B7 -- no recommendation endpoint exists. Empty renders "No suggestions
    // right now", which is true; the mock's authored suggestions are not.
    return Promise.resolve([]);
  }

  createClass(_name: string, _grade: Grade): Promise<CreateClassResult> {
    // B6.4. A class created in the mock would vanish on the next refetch and
    // show a class key that exists nowhere.
    return Promise.reject(new Error("Creating a class is not available yet."));
  }

  getJoinRequests(_classId: string): Promise<PendingRequestDisplay[]> {
    return Promise.reject(new Error("Join requests are not available yet."));
  }

  approveJoinRequest(_classId: string, _requestId: string): Promise<void> {
    return Promise.reject(new Error("Join requests are not available yet."));
  }

  rejectJoinRequest(_classId: string, _requestId: string): Promise<void> {
    return Promise.reject(new Error("Join requests are not available yet."));
  }

  async getClassReports(classId: string): Promise<ClassReportsResponse> {
    const w = await get<WireReport>(`/classes/${encodeURIComponent(classId)}/reports`);
    return {
      disclosure: w.disclosure,
      className: w.class_name ?? "",
      // No served series -- QUESTIONS_FOR_ML_TEAM_3 Q4. Empty renders the
      // chart's own "not enough data yet" sentence.
      classLearningProgress: { sessionNumbers: [], values: [] },
      earlyWarningTrend: {
        sessionNumbers: w.early_warning_curve.map((p) => p.t),
        flagRates: w.early_warning_curve.map((p) => p.flag_rate),
        explanation: EARLY_WARNING_TREND_EXPLANATION,
      },
      participation: w.participation.map((p) => ({
        bucketLabel: p.bucket_label,
        studentCount: p.student_count,
      })),
    };
  }
}
