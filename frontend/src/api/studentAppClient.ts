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

import { DuplicateClassNameError, type Grade } from "../lib/presentation";
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
