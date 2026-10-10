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
// 2. EVERY FAILURE REJECTS AS AN Error, so ErrorState renders. Nothing throws
//    synchronously. The rejection carries the HTTP status (`apiError`) because
//    a 403 is not a retryable failure and must not be offered as one -- see
//    lib/apiError.ts.
// 3. The screens still re-apply sortCohortOrder / toWatchStatus /
//    filterExplanation. Nothing here relies on the backend's ordering.

import type {
  ApiClient,
  ReadOptions,
  ClassReportsResponse,
  CohortResponse,
  CreateClassResult,
  ClassStudentOverview,
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
import type {
  Grade,
  ModifiedAction,
  PendingRequestDisplay,
  RecommendationDisplay,
} from "../lib/presentation";
import {
  EARLY_WARNING_TREND_EXPLANATION,
  RecommendationConflictError,
  watchCountAfterHandled,
  modifiedActionSummary,
  recommendationSourceLabel,
  skillDisplayName,
} from "../lib/presentation";
import { apiError } from "../lib/apiError";
import * as studentApp from "./studentAppClient";
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
  suggestion_status: "accepted" | "modified" | null;
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
    handled_count: number;
  }[];
}

interface WireCohort {
  disclosure: string;
  classroom_id: string;
  class_name: string | null;
  grade: Grade | null;
  class_key: string | null;
  pending_request_count: number;
  stats: {
    learner_count: number;
    watch_count: number;
    getting_started_count: number;
    handled_count: number;
  };
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
    /** D42: latest mastery, 0-1, rounded to 2 decimals. Bar only, never a number. */
    mastery_level: number | null;
    /** D46: never practised in any session -- no measurement exists. */
    never_practised: boolean;
  }[];
}

/** D42: mastery_level is on a fixed 0-1 scale, so every skill's bar uses the
 * same bounds -- a bar's length means the same thing on every row. */
const MASTERY_BOUNDS = { min: 0, max: 1 };

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

interface WireRecommendation {
  recommendation_id: string;
  expires_after_session: number;
  trigger: { type: string; skill: string | null };
  proposed_action: WireAction;
  evidence_summary: string;
  teacher_status: "pending" | "accepted" | "dismissed" | "modified";
  teacher_modified_action: WireAction | null;
}

interface WireRecommendations {
  recommendations: WireRecommendation[];
}

interface WireClassOverviews {
  classroom_id: string;
  students: {
    detail: WireStudent;
    skills: WireSkills;
    recommendations: WireRecommendations;
  }[];
}

function actionSkill(action: WireAction | null): string | null {
  const skill = action?.detail?.skill;
  return typeof skill === "string" ? skill : null;
}

function toRecommendationDisplay(r: WireRecommendation): RecommendationDisplay {
  const skillId = actionSkill(r.proposed_action) ?? r.trigger.skill ?? null;
  const modified = r.teacher_modified_action;
  return {
    recommendationId: r.recommendation_id,
    kind: r.proposed_action.kind,
    targetSkillId: skillId,
    targetSkillDisplayName: skillDisplayName(skillId),
    sourceLabel: recommendationSourceLabel(r.trigger.type),
    evidenceSummary: r.evidence_summary,
    status: r.teacher_status,
    modifiedActionSummary: modified
      ? modifiedActionSummary(modified.kind, actionSkill(modified))
      : null,
    expiresAfterSession: r.expires_after_session,
  };
}

interface WireReport {
  disclosure: string;
  class_name: string | null;
  early_warning_curve: { t: number; flag_rate: number }[];
  participation: { bucket_label: string; student_count: number }[];
}

// --- transport ---------------------------------------------------------------

/**
 * POST a teacher decision. A 409 becomes RecommendationConflictError with the
 * server's named reason ("already_decided" | "expired"), so the screen can say
 * which; every other failure is a plain Error.
 */
async function postJson(path: string, body?: unknown): Promise<Response> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (supabase) {
    const { data } = await supabase.auth.getSession();
    const token = data.session?.access_token;
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  return fetch(`${API_BASE}${PREFIX}${path}`, {
    method: "POST",
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

/** A plain POST: any non-2xx is a plain Error. Used for writes with no
 * meaning attached to 409 -- minting a class key, for instance, which is
 * idempotent and has no conflict state. */
async function post<T>(path: string, body?: unknown): Promise<T> {
  const response = await postJson(path, body);
  if (!response.ok) {
    throw apiError(path, response.status);
  }
  return (await response.json()) as T;
}

async function postDecision<T>(path: string, body?: unknown): Promise<T> {
  const response = await postJson(path, body);
  if (response.status === 409) {
    let reason = "already_decided";
    try {
      const payload = (await response.json()) as { detail?: { error?: unknown } };
      if (typeof payload.detail?.error === "string") reason = payload.detail.error;
    } catch {
      // An unreadable body is still a conflict.
    }
    throw new RecommendationConflictError(reason);
  }
  if (!response.ok) {
    throw apiError(path, response.status);
  }
  return (await response.json()) as T;
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (supabase) {
    const { data } = await supabase.auth.getSession();
    const token = data.session?.access_token;
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  // Bearer only, never a cookie: the API sets allow_credentials=False.
  // `signal` is passed only by the background warm-up, so a request for a page
  // the teacher has navigated away from is actually cancelled, not merely
  // ignored -- an ignored request still holds the connection.
  const response = await fetch(`${API_BASE}${PREFIX}${path}`, { headers, signal });
  if (!response.ok) {
    throw apiError(path, response.status);
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
    suggestionStatus: card.suggestion_status ?? null,
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

/** Detail + skills -> the student screen's one object. The single-learner path and the
 * class overview both use this, so a learner cannot render differently depending on
 * which request filled the cache. */
function toStudentOverview(detail: WireStudent, skills: WireSkills): StudentOverviewResponse {
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
        // D42: the bar is the latest mastery value. Null (no stored value)
        // draws no bar rather than an empty one.
        relativeLevel: s.mastery_level,
        practiceCount: s.practice_count,
        neverPractised: s.never_practised,
      })),
    disclosure: detail.disclosure,
    className: detail.class_name ?? "",
    skillBounds: Object.fromEntries(skills.skills.map((s) => [s.skill, MASTERY_BOUNDS])),
  };
}

export class HttpClient implements ApiClient {
  async getHome(): Promise<HomeSummary> {
    const w = await get<WireHome>("/home");
    return {
      teacherName: w.teacher_name ?? "",
      // D50: flagged minus handled, everywhere a watch count is shown.
      studentsToWatch: watchCountAfterHandled(
        w.watch_count,
        w.classes.reduce((sum, c) => sum + (c.handled_count ?? 0), 0),
      ),
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
        toWatchCount: watchCountAfterHandled(c.watch_count, c.handled_count),
        pendingRequestCount: c.pending_request_count,
        handledCount: c.handled_count ?? 0,
      })),
      disclosure: w.disclosure,
    };
  }

  async getCohort(classId: string, opts?: ReadOptions): Promise<CohortResponse> {
    const w = await get<WireCohort>(
      `/classes/${encodeURIComponent(classId)}/cohort`,
      opts?.signal,
    );
    return {
      classId: w.classroom_id,
      className: w.class_name ?? "",
      studentCount: w.stats.learner_count,
      toWatchCount: watchCountAfterHandled(w.stats.watch_count, w.stats.handled_count),
      handledCount: w.stats.handled_count ?? 0,
      gettingStartedCount: w.stats.getting_started_count,
      pendingRequestCount: w.pending_request_count,
      students: withoutPriority(w.learners.map(toSnapshot)),
      disclosure: w.disclosure,
      grade: w.grade ?? "GRADE_2",
      // Empty only when no key has been minted (backend/scripts/mint_class_keys.py).
      classKey: w.class_key ?? "",
    };
  }

  async getClassWatchList(classId: string, opts?: ReadOptions): Promise<WatchListResponse> {
    const w = await get<WireWatch>(
      `/classes/${encodeURIComponent(classId)}/watch`,
      opts?.signal,
    );
    return {
      totalStudents: w.total_students,
      disclosure: w.disclosure,
      // D50: a learner whose suggestion is handled leaves the watch list, so
      // the list matches the deducted count. They remain on the class page,
      // blue, under All Students.
      students: withoutPriority(w.learners.map(toSnapshot)).filter((s) => !s.suggestionStatus),
    };
  }

  async getWatchList(opts?: ReadOptions): Promise<WatchListResponse> {
    const w = await get<WireWatch>("/watch", opts?.signal);
    return {
      totalStudents: w.total_students,
      disclosure: w.disclosure,
      // D50: a learner whose suggestion is handled leaves the watch list, so
      // the list matches the deducted count. They remain on the class page,
      // blue, under All Students.
      students: withoutPriority(w.learners.map(toSnapshot)).filter((s) => !s.suggestionStatus),
    };
  }

  async getStudentOverview(studentId: string): Promise<StudentOverviewResponse> {
    const id = encodeURIComponent(studentId);
    const [detail, skills] = await Promise.all([
      get<WireStudent>(`/students/${id}`),
      get<WireSkills>(`/students/${id}/skills`),
    ]);
    return toStudentOverview(detail, skills);
  }

  async getClassStudentOverviews(
    classId: string,
    opts?: ReadOptions,
  ): Promise<ClassStudentOverview[]> {
    const w = await get<WireClassOverviews>(
      `/classes/${encodeURIComponent(classId)}/students/overview`,
      opts?.signal,
    );
    return w.students.map((st) => ({
      studentId: st.detail.student_id,
      overview: toStudentOverview(st.detail, st.skills),
      recommendations: st.recommendations.recommendations.map(toRecommendationDisplay),
    }));
  }

  async getStudentSessions(studentId: string, opts?: ReadOptions): Promise<SessionEntry[]> {
    const w = await get<WireSessions>(
      `/students/${encodeURIComponent(studentId)}/sessions`,
      opts?.signal,
    );
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
    // D35: the one generated suggestion (practice on a stagnant skill, for a
    // watch-flagged learner). `active` includes accepted/modified ones, which
    // render as decided -- see recommendationDecisionLine.
    const w = await get<WireRecommendations>(
      `/students/${encodeURIComponent(studentId)}/recommendations?status=active`,
    );
    return w.recommendations.map(toRecommendationDisplay);
  }

  async acceptRecommendation(recommendationId: string): Promise<RecommendationDisplay> {
    return toRecommendationDisplay(
      await postDecision<WireRecommendation>(`/recommendations/${encodeURIComponent(recommendationId)}/accept`),
    );
  }

  async dismissRecommendation(recommendationId: string): Promise<RecommendationDisplay> {
    return toRecommendationDisplay(
      await postDecision<WireRecommendation>(`/recommendations/${encodeURIComponent(recommendationId)}/dismiss`),
    );
  }

  async modifyRecommendation(
    recommendationId: string,
    action: ModifiedAction,
  ): Promise<RecommendationDisplay> {
    return toRecommendationDisplay(
      await postDecision<WireRecommendation>(
        `/recommendations/${encodeURIComponent(recommendationId)}/modify`,
        {
          teacher_modified_action: {
            kind: action.kind,
            detail: action.skillId ? { skill: action.skillId } : {},
          },
        },
      ),
    );
  }

  /**
   * B6.4, two steps against two services, in this order:
   *
   * 1. the STUDENT APP creates the classroom -- it owns classrooms, and Component 3 never
   *    writes that table (D3/D10);
   * 2. Component 3 mints the classroom's PERMANENT key (D1) in its own table.
   *
   * If step 2 fails the class still exists, correctly, with no key yet; the cohort screen shows
   * no key and the next attempt mints one. The reverse order is impossible -- there is nothing
   * to attach a key to -- and a key is never rotated to "repair" anything.
   */
  async deleteClass(classId: string, confirmationName: string): Promise<void> {
    // Straight to the student app: Component 3 never writes classrooms (D3/D10).
    await studentApp.deleteClassroom(classId, confirmationName);
  }

  async createClass(name: string, grade: Grade): Promise<CreateClassResult> {
    const created = await studentApp.createClassroom(name, grade);

    // The join code is the STUDENT APP's invite token (D49). It used to be a code
    // Component 3 minted itself, which matched no invite and which no child could
    // ever redeem. The student app shows the plaintext once and keeps only its
    // hash, so it has to be handed straight to Component 3 to be stored.
    const invite = await studentApp.createInvite(created.classroom_id);
    if (invite.invite_token === null) {
      // The classroom already had a live code whose plaintext we cannot re-read.
      // Never invent one: ask Component 3 for the copy it stored.
      const existing = await post<{ class_key: string }>(
        `/classes/${encodeURIComponent(created.classroom_id)}/key`,
      );
      return {
        classId: created.classroom_id,
        className: created.name ?? name,
        grade: created.grade ?? grade,
        classKey: existing.class_key,
      };
    }

    let key: { class_key: string };
    try {
      key = await post<{ class_key: string }>(
        `/classes/${encodeURIComponent(created.classroom_id)}/key`,
        { invite_token: invite.invite_token },
      );
    } catch (error) {
      // A live code nobody holds the plaintext of is worse than no code: the
      // teacher cannot read it out and it cannot be replaced while it is live.
      // Kill it, so a retry can mint a fresh one.
      await studentApp.revokeInvite(invite.classroom_invite_id).catch(() => undefined);
      throw error;
    }

    return {
      classId: created.classroom_id,
      className: created.name ?? name,
      grade: created.grade ?? grade,
      classKey: key.class_key,
    };
  }

  async getJoinRequests(classId: string): Promise<PendingRequestDisplay[]> {
    const requests = await studentApp.listMembershipRequests(classId);
    return requests
      // The endpoint returns decided requests too; the screen is a queue of what is waiting.
      .filter((r) => r.state === "PENDING")
      .map((r) => ({
        requestId: r.classroom_membership_id,
        studentDisplayName: r.learner_name ?? "",
        requestedDate: r.requested_at_utc,
      }));
  }

  approveJoinRequest(_classId: string, requestId: string): Promise<void> {
    // Addressed by MEMBERSHIP id, not by class: the student app's own route shape.
    return studentApp.approveMembership(requestId);
  }

  rejectJoinRequest(_classId: string, requestId: string): Promise<void> {
    return studentApp.rejectMembership(requestId);
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
