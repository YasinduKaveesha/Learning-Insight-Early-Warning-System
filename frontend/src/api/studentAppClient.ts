// The STUDENT APP's own API (B6.4) — classrooms and join requests.
//
// WHY THESE CALLS DO NOT GO TO COMPONENT 3. Classrooms, memberships and join
// decisions belong to the student application; Component 3 is read-only toward
// them (D3/D10) and must never write those tables. backend_plan §8 says it in
// one line: "Reuse, do not rebuild — the dashboard calls those." So the
// dashboard asks the student app directly, with the SAME Supabase token the
// teacher signed in with. Component 3 is involved in exactly one part of class
// creation: minting the permanent class key for its own t3_classroom_keys.
//
// Every POST here needs an Idempotency-Key header (the student app returns 422
// without one), so a retry replays instead of creating a second classroom or
// approving a child twice.

import {
  DuplicateClassNameError,
  isDuplicateClassNameError,
  type Grade,
} from "../lib/presentation";
import { supabase } from "./supabaseClient";

const BASE: string = (
  import.meta.env.VITE_STUDENT_APP_BASE_URL ?? "http://localhost:8000"
).replace(/\/$/, "");
const PREFIX = "/api/v1";

export interface ClassroomCreated {
  classroom_id: string;
  name: string | null;
  grade: Grade;
}

export interface InviteCreated {
  classroom_invite_id: string;
  /** Plaintext, shown once. Null when this replayed an already-issued invite. */
  invite_token: string | null;
  token_already_issued: boolean;
  /** Null: a classroom join code does not expire (D49). */
  expires_at_utc: string | null;
}

export interface MembershipRequest {
  classroom_membership_id: string;
  learner_name: string | null;
  state: string;
  requested_at_utc: string;
}

/** A fresh key per logical operation. `randomUUID` is absent in some test and
 * older-browser environments, so there is a fallback -- a missing header is a
 * 422, which would look like a bug in the form. */
function idempotencyKey(): string {
  const uuid = globalThis.crypto?.randomUUID?.();
  return uuid ?? `t3-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

async function headers(withBody: boolean): Promise<Record<string, string>> {
  const out: Record<string, string> = { Accept: "application/json" };
  if (withBody) out["Content-Type"] = "application/json";
  if (supabase) {
    const { data } = await supabase.auth.getSession();
    const token = data.session?.access_token;
    if (token) out.Authorization = `Bearer ${token}`;
  }
  return out;
}

async function request<T>(
  path: string,
  init: { method: "GET" | "POST"; body?: unknown } = { method: "GET" },
): Promise<T> {
  const hasBody = init.body !== undefined;
  const h = await headers(hasBody);
  if (init.method === "POST") h["Idempotency-Key"] = idempotencyKey();

  const response = await fetch(`${BASE}${PREFIX}${path}`, {
    method: init.method,
    headers: h,
    body: hasBody ? JSON.stringify(init.body) : undefined,
  });

  if (!response.ok) {
    // 409 CONFLICT on class creation is a duplicate name (the student app
    // enforces per-teacher uniqueness, case-insensitively). The screen shows
    // that inline on the field; everything else is a generic failure.
    if (response.status === 409) {
      throw new DuplicateClassNameError("A class with that name already exists.");
    }
    throw new Error(`Student app request to ${path} failed with HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function createClassroom(name: string, grade: Grade): Promise<ClassroomCreated> {
  return request<ClassroomCreated>("/classrooms", { method: "POST", body: { name, grade } });
}

/** Mint the classroom's join code (D49).
 *
 * `invite_token` is the plaintext code, and the student app shows it EXACTLY
 * ONCE -- it keeps only a SHA-256. If it is not handed to Component 3 and
 * stored, no one can ever read it again and the classroom needs a new one.
 * `token_already_issued` comes back true when the classroom already had a live
 * code, and then `invite_token` is null for that same reason.
 */
export async function createInvite(classroomId: string): Promise<InviteCreated> {
  return request<InviteCreated>(
    `/classrooms/${encodeURIComponent(classroomId)}/invites`,
    { method: "POST", body: {} },
  );
}

/** Kill a code. Used when a mint succeeded but storing the plaintext failed:
 * a live code nobody can read is worse than no code at all. */
export async function revokeInvite(classroomInviteId: string): Promise<void> {
  await request(`/classroom-invites/${encodeURIComponent(classroomInviteId)}/revoke`, {
    method: "POST",
    body: {},
  });
}

export async function listMembershipRequests(classroomId: string): Promise<MembershipRequest[]> {
  const body = await request<{ requests: MembershipRequest[] }>(
    `/classrooms/${encodeURIComponent(classroomId)}/membership-requests`,
  );
  return body.requests ?? [];
}

export async function approveMembership(membershipId: string): Promise<void> {
  await request(`/classroom-memberships/${encodeURIComponent(membershipId)}/approve`, {
    method: "POST",
    body: {},
  });
}

export async function rejectMembership(membershipId: string): Promise<void> {
  await request(`/classroom-memberships/${encodeURIComponent(membershipId)}/reject`, {
    method: "POST",
    body: {},
  });
}

/** Create this account's TEACHER profile in the student app (B6.4).
 *
 * Signing up with Supabase only creates an identity. A teacher also needs a
 * `teacher_profiles` row, and only the student app may write one (D3) -- without
 * it the dashboard answers 403 for every request, which reads as "your login is
 * broken" rather than "your account is not a teacher yet".
 *
 * `profile_type` is set ONCE and irreversibly by this call, so a 409 means the
 * profile already exists and is treated as success -- never as a reason to retry
 * with different data.
 */
export async function createTeacherProfile(name: string): Promise<void> {
  try {
    await request("/teacher/profile", { method: "POST", body: { name } });
  } catch (e) {
    // `request` maps 409 to DuplicateClassNameError (its only 409 caller until
    // now). Here a 409 means "already a teacher", which is the desired end state.
    if (isDuplicateClassNameError(e)) return;
    throw e;
  }
}
