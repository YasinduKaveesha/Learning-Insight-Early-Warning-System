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
import { EARLY_WARNING_TREND_EXPLANATION, recommendationLabel } from "../lib/presentation";
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

interface WireAction {
  kind: string;
  detail: { skill?: unknown } & Record<string, unknown>;
}

interface WireRecommendations {
  recommendations: {
    recommendation_id: string;
    expires_after_session: number;
    trigger: { type: string; skill: string | null };
    proposed_action: WireAction;
    evidence_summary: string;
    teacher_status: "pending" | "accepted" | "dismissed" | "modified";
    teacher_modified_action: WireAction | null;
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
 * D39: NO PRIORITY NUMBER, AND NO RANKED ORDER, across mixed sessions.
 *
 * rank_within_t ranks a learner only against others at the SAME session, and
 * the score behind it shifts with the session number. A class mixes sessions,
 * so any class-wide order built from it -- including the (t, rank) numbering
 * this client used before -- is mostly a session ordering (Spearman 0.877 with
 * session in the demo) presented as "Priority N". MODEL_CARD section 10 scopes
 * ordering to one snapshot, and a numbered list over the 2+ score is the
 * interface form of the rank cut D5 prevents.
 *
 * So the rank is dropped here, before any screen can see it, and flagged
 * learners are listed by name. toWatchStatus then yields priority: null, and
 * StudentDetail shows the snapshot framing line instead of a badge.
 */
function withoutPriority(snapshots: LearnerSnapshot[]): LearnerSnapshot[] {
  return snapshots
    .map((s) => ({ ...s, rankWithinSnapshot: null }))
    .sort((a, b) => a.displayName.localeCompare(b.displayName));
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
      students: withoutPriority(w.learners.map(toSnapshot)),
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
      students: withoutPriority(w.learners.map(toSnapshot)),
    };
  }

  async getWatchList(): Promise<WatchListResponse> {
    const w = await get<WireWatch>("/watch");
    return {
      totalStudents: w.total_students,
      disclosure: w.disclosure,
      students: withoutPriority(w.learners.map(toSnapshot)),
    };
  }

  async getStudentOverview(studentId: string): Promise<StudentOverviewResponse> {
    const id = encodeURIComponent(studentId);
    const [detail, skills] = await Promise.all([
      get<WireStudent>(`/students/${id}`),
      get<WireSkills>(`/students/${id}/skills`),
    ]);

    const snapshot: LearnerSnapshot = {
      studentId: detail.student_id,
      displayName: detail.display_name,
      classId: detail.classroom_id ?? "",
      sessionNumber: detail.t,
      watchFlag: detail.watch_flag,
      rankWithinSnapshot: null, // D39 -- see withoutPriority
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

  async getStudentRecommendations(studentId: string): Promise<RecommendationDisplay[]> {
    // B7. Real endpoint, and today it is always empty: nothing generates a
    // recommendation until the ML team rules on the trigger -> action mapping
    // (dev_docs/QUESTIONS_FOR_ML_TEAM_4.md). Empty renders "No suggestions
    // right now", which is true.
    //
    // Accept / dismiss / modify on the card still update only this screen's
    // local state: ApiClient has no method to persist a decision yet. The
    // backend endpoints exist (POST /recommendations/{id}/accept|dismiss|modify).
    const w = await get<WireRecommendations>(
      `/students/${encodeURIComponent(studentId)}/recommendations?status=active`,
    );
    return w.recommendations.map((r) => {
      const skill = r.proposed_action.detail.skill ?? r.trigger.skill ?? null;
      const modified = r.teacher_modified_action;
      return {
        recommendationId: r.recommendation_id,
        kind: r.proposed_action.kind,
        targetSkillDisplayName:
          typeof skill === "string" ? (SKILL_DISPLAY_NAME[skill] ?? skill) : "",
        evidenceSummary: r.evidence_summary,
        status: r.teacher_status,
        modifiedActionSummary: modified ? recommendationLabel(modified.kind) : null,
        expiresAfterSession: r.expires_after_session,
      };
    });
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
